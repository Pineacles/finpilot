"""FinBERT news sentiment service.

Lazy-loads ProsusAI/finbert on first call, caches in module-global.
In-memory result cache per symbol, TTL 30 minutes.
"""
import time
import logging
from datetime import datetime, timezone, timedelta
from statistics import mean, stdev

logger = logging.getLogger(__name__)

# Module-level singletons (lazy-loaded on first call)
_tokenizer = None
_model = None
_model_load_failed = False

# In-memory cache: symbol -> (result_dict, timestamp)
_cache: dict = {}
CACHE_TTL = 1800  # 30 minutes


def _load_model():
    """Load FinBERT tokenizer and model. Sets _model_load_failed on error."""
    global _tokenizer, _model, _model_load_failed
    if _model is not None or _model_load_failed:
        return
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch  # noqa: F401  — ensure torch is importable
        logger.info("Loading ProsusAI/finbert model...")
        _tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        _model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        _model.eval()
        logger.info("FinBERT model loaded successfully.")
    except Exception as exc:
        logger.error("Failed to load FinBERT model: %s", exc)
        _model_load_failed = True


def _score_headline(title: str) -> dict:
    """Run FinBERT on a single headline. Returns {positive, neutral, negative}."""
    import torch
    import torch.nn.functional as F

    inputs = _tokenizer(title, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = _model(**inputs).logits
    probs = F.softmax(logits, dim=-1).squeeze().tolist()
    # FinBERT label order: positive=0, negative=1, neutral=2
    # Verify by checking model.config.id2label
    id2label = _model.config.id2label  # {0: 'positive', 1: 'negative', 2: 'neutral'}
    label_map = {v.lower(): probs[k] for k, v in id2label.items()}
    return label_map


def _polarity(scores: dict) -> float:
    """pos - neg in [-1, 1]."""
    return scores.get("positive", 0.0) - scores.get("negative", 0.0)


async def analyze_symbol_sentiment(symbol: str, days: int = 7) -> dict:
    """
    Fetch news for `symbol`, run FinBERT, return sentiment metrics.
    Returns error dict if model failed to load or no news returned.
    """
    cache_key = f"{symbol}:{days}"
    now = time.monotonic()
    if cache_key in _cache:
        result, ts = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return result

    # Ensure model is loaded
    _load_model()
    if _model_load_failed:
        result = {"symbol": symbol, "error": "model_load_failed", "news_count": 0}
        _cache[cache_key] = (result, now)
        return result

    # Fetch news via yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []
    except Exception as exc:
        logger.warning("yfinance news fetch failed for %s: %s", symbol, exc)
        raw_news = []

    if not raw_news:
        result = {"symbol": symbol, "error": "no_data", "news_count": 0}
        _cache[cache_key] = (result, now)
        return result

    # Filter to last `days` days, cap at 30
    # yfinance ≥0.2.50 nests data under item["content"]; older format uses top-level keys
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []
    for item in raw_news:
        content = item.get("content") or item  # new nested format or old flat format
        # New format uses ISO pubDate string; old format uses unix providerPublishTime
        pub_date_str = content.get("pubDate") or content.get("displayTime") or ""
        ts_unix = item.get("providerPublishTime") or 0
        if pub_date_str:
            try:
                published = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except ValueError:
                published = datetime.now(timezone.utc)
        elif ts_unix:
            published = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
        else:
            published = datetime.now(timezone.utc)
        if published >= cutoff:
            filtered.append((content, published))
    # Sort newest first, cap at 30
    filtered.sort(key=lambda x: x[1], reverse=True)
    filtered = filtered[:30]

    if not filtered:
        result = {"symbol": symbol, "error": "no_data", "news_count": 0}
        _cache[cache_key] = (result, now)
        return result

    # Score each headline
    headlines = []
    for content, published in filtered:
        title = content.get("title") or ""
        if not title:
            continue
        try:
            scores = _score_headline(title)
            pol = _polarity(scores)
        except Exception as exc:
            logger.warning("Scoring failed for headline '%s': %s", title[:60], exc)
            pol = 0.0
            scores = {"positive": 0.0, "neutral": 1.0, "negative": 0.0}

        source = ""
        publisher = content.get("provider") or content.get("publisher") or content.get("source") or {}
        if isinstance(publisher, dict):
            source = publisher.get("displayName") or publisher.get("name") or ""
        elif isinstance(publisher, str):
            source = publisher

        # URL: new format uses canonicalUrl.url or clickThroughUrl.url
        link = content.get("link") or content.get("url") or ""
        if not link:
            canonical = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
            if isinstance(canonical, dict):
                link = canonical.get("url") or ""

        headlines.append({
            "title": title,
            "polarity": round(pol, 4),
            "positive": round(scores.get("positive", 0.0), 4),
            "neutral": round(scores.get("neutral", 0.0), 4),
            "negative": round(scores.get("negative", 0.0), 4),
            "source": source,
            "published_at": published.isoformat(),
            "link": link,
        })

    if not headlines:
        result = {"symbol": symbol, "error": "no_data", "news_count": 0}
        _cache[cache_key] = (result, now)
        return result

    polarities = [h["polarity"] for h in headlines]
    mean_tone = round(mean(polarities), 4)
    dispersion = round(stdev(polarities) if len(polarities) > 1 else 0.0, 4)

    # Daily aggregation for sparkline
    daily_map: dict = {}
    for _content, published in filtered[:len(headlines)]:
        day = published.date().isoformat()
        if day not in daily_map:
            daily_map[day] = []
    # Re-associate polarities with dates
    for h in headlines:
        day = h["published_at"][:10]
        if day not in daily_map:
            daily_map[day] = []
        daily_map[day].append(h["polarity"])

    daily = [
        {"date": d, "mean_polarity": round(mean(pols), 4), "count": len(pols)}
        for d, pols in sorted(daily_map.items())
        if pols
    ]

    # polarity_shift: mean of last 2 days - mean of prior days
    if len(daily) >= 2:
        recent_pols = []
        for d in daily[-2:]:
            recent_pols.extend([d["mean_polarity"]] * d["count"])
        prior_pols = []
        for d in daily[:-2]:
            prior_pols.extend([d["mean_polarity"]] * d["count"])
        polarity_shift = round(mean(recent_pols) - (mean(prior_pols) if prior_pols else 0.0), 4)
    else:
        polarity_shift = 0.0

    result = {
        "symbol": symbol,
        "mean_tone": mean_tone,
        "dispersion": dispersion,
        "polarity_shift": polarity_shift,
        "news_count": len(headlines),
        "daily": daily,
        "headlines": headlines,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "model": "ProsusAI/finbert",
    }
    _cache[cache_key] = (result, time.monotonic())
    return result
