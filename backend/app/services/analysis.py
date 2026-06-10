"""AI-powered market analysis service.

Uses yfinance for market data and Claude (or custom endpoint) for analysis.
Settings are read from DB first, env var fallback.

If `analysis_endpoint` is set, it POSTs to that URL instead of Anthropic —
so you can point it at your own AI agent.
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import anthropic
import httpx
import yfinance as yf
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.models.stock import StockPosition, MarketAnalysis
from app.services.settings import get_setting


SYSTEM_PROMPTS = {
    "macro": """You are a macro-economic analyst. Analyze economic indicators and their impact
on the user's stock portfolio. Focus on: interest rates (10Y yield), volatility (VIX),
S&P 500 trends, and how these affect different sectors. Be specific and actionable.
Consider the current market regime and where we are in the economic cycle.""",

    "sector": """You are a sector analyst. Analyze the user's portfolio allocation across sectors.
Identify concentration risks, sector rotation opportunities, and how current market conditions
favor or disfavor their sector exposure. Use the sector/industry data provided for each position.
Be specific and actionable.""",

    "position": """You are a multi-agent financial analyst combining technical, fundamental, and
sentiment perspectives. For each position in the user's portfolio:
1. Technical: Analyze recent price action, SMA crossovers, volume trends
2. Fundamental: Evaluate PE ratio, dividend yield, market cap
3. Risk: Assess position sizing and portfolio concentration
Provide a clear buy/hold/trim recommendation with reasoning.""",
}

ANALYSIS_USER_MSG = """Analyze this portfolio data:

{data}

Provide your analysis in the following JSON structure:
{{
  "summary": "2-3 sentence executive summary",
  "risk_level": "low|medium|high",
  "key_insights": ["insight1", "insight2", ...],
  "recommendations": ["recommendation1", "recommendation2", ...],
  "sector_breakdown": {{"sector": "assessment"}},
  "position_notes": {{"symbol": "note"}},
  "macro_outlook": "brief macro outlook"
}}

Return ONLY valid JSON, no markdown or explanation."""


async def fetch_market_data_for_positions(positions: list[StockPosition]) -> dict:
    """Fetch market data using yfinance for the user's positions."""
    data = {
        "positions": [],
        "market_overview": {},
        "economic_indicators": {},
    }

    for pos in positions:
        pos_data = {
            "symbol": pos.symbol,
            "name": pos.name,
            "quantity": pos.quantity,
            "avg_cost": pos.avg_cost_price,
            "current_price": pos.last_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "currency": pos.currency,
        }

        try:
            ticker = yf.Ticker(pos.symbol)
            hist = ticker.history(period="3mo")
            if not hist.empty:
                recent = hist.tail(30)
                pos_data["price_history_30d"] = [
                    {"date": str(idx.date()), "close": round(row["Close"], 2), "volume": int(row["Volume"])}
                    for idx, row in recent.iterrows()
                ]
                if len(hist) >= 50:
                    pos_data["sma_50"] = round(hist["Close"].rolling(50).mean().iloc[-1], 2)
                if len(hist) >= 20:
                    pos_data["sma_20"] = round(hist["Close"].rolling(20).mean().iloc[-1], 2)

                info = ticker.info
                pos_data["sector"] = info.get("sector", "Unknown")
                pos_data["industry"] = info.get("industry", "Unknown")
                pos_data["pe_ratio"] = info.get("trailingPE")
                pos_data["market_cap"] = info.get("marketCap")
                pos_data["dividend_yield"] = info.get("dividendYield")
        except Exception as _exc:
            logger.warning("Failed to fetch market data for position: %s", _exc)
            pos_data["price_history_30d"] = []

        data["positions"].append(pos_data)

    # S&P 500
    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1mo")
        if not spy_hist.empty:
            data["market_overview"]["sp500_30d"] = [
                {"date": str(idx.date()), "close": round(row["Close"], 2)}
                for idx, row in spy_hist.iterrows()
            ]
            data["market_overview"]["sp500_change_1m"] = round(
                (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[0] - 1) * 100, 2
            )
    except Exception as _exc:
        logger.warning("Failed to fetch S&P 500 data: %s", _exc)

    # 10Y Treasury
    try:
        tnx = yf.Ticker("^TNX")
        tnx_hist = tnx.history(period="5d")
        if not tnx_hist.empty:
            data["economic_indicators"]["us_10y_yield"] = round(tnx_hist["Close"].iloc[-1], 2)
    except Exception as _exc:
        logger.warning("Failed to fetch 10Y Treasury data: %s", _exc)

    # VIX
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        if not vix_hist.empty:
            data["economic_indicators"]["vix"] = round(vix_hist["Close"].iloc[-1], 2)
    except Exception as _exc:
        logger.warning("Failed to fetch VIX data: %s", _exc)

    return data


async def run_analysis_via_anthropic(
    market_data: dict, analysis_type: str, api_key: str, model: str
) -> dict:
    """Run analysis via Anthropic API."""
    client = anthropic.Anthropic(api_key=api_key)
    system = SYSTEM_PROMPTS.get(analysis_type, SYSTEM_PROMPTS["position"])
    user_msg = ANALYSIS_USER_MSG.format(data=json.dumps(market_data, indent=2, default=str))

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    return _parse_response(response.content[0].text)


async def run_analysis_via_custom_endpoint(
    market_data: dict, analysis_type: str, endpoint: str,
    auth_header: str = "", model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Run analysis via custom endpoint (user's own AI agent)."""
    system = SYSTEM_PROMPTS.get(analysis_type, SYSTEM_PROMPTS["position"])
    user_msg = ANALYSIS_USER_MSG.format(data=json.dumps(market_data, indent=2, default=str))

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            endpoint,
            headers=headers,
            json={
                "analysis_type": analysis_type,
                "model": model,
                "market_data": market_data,
                "system_prompt": system,
                "user_prompt": user_msg,
            },
        )
        resp.raise_for_status()
        result = resp.json()

    # If the endpoint returns the analysis directly
    if "summary" in result:
        return result
    # If it wraps in a content field
    if "content" in result:
        return result["content"] if isinstance(result["content"], dict) else _parse_response(str(result["content"]))
    # If it returns raw text
    if "text" in result:
        return _parse_response(result["text"])

    return result


def _parse_response(text: str) -> dict:
    """Parse AI response text into structured dict."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": text[:500],
            "risk_level": "unknown",
            "key_insights": [],
            "recommendations": [],
            "raw_response": text,
        }


async def generate_analysis(
    db: AsyncSession,
    user_id: str,
    analysis_type: str = "position",
) -> MarketAnalysis:
    """Full pipeline: fetch data -> run analysis -> store result."""
    # Get user's positions
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = result.scalars().all()
    market_data = await fetch_market_data_for_positions(positions)

    # Read settings from DB
    custom_endpoint = await get_setting(db, user_id, "analysis_endpoint")
    auth_header = await get_setting(db, user_id, "analysis_auth_header")
    api_key = await get_setting(db, user_id, "anthropic_api_key")
    model = await get_setting(db, user_id, "analysis_model") or "claude-sonnet-4-20250514"

    # Route to custom endpoint or Anthropic
    if custom_endpoint:
        analysis_content = await run_analysis_via_custom_endpoint(
            market_data, analysis_type, custom_endpoint, auth_header, model
        )
        model_used = f"{model} via {custom_endpoint}"
    elif api_key:
        analysis_content = await run_analysis_via_anthropic(market_data, analysis_type, api_key, model)
        model_used = model
    else:
        raise RuntimeError("No analysis backend configured. Set an Anthropic API key or custom endpoint in Settings.")

    analysis = MarketAnalysis(
        user_id=user_id,
        analysis_type=analysis_type,
        content=analysis_content,
        model_used=model_used,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


async def get_latest_analysis(
    db: AsyncSession,
    user_id: str,
    analysis_type: str | None = None,
) -> list[MarketAnalysis]:
    """Get the most recent analysis for each type."""
    types = [analysis_type] if analysis_type else ["macro", "sector", "position"]
    results = []
    for t in types:
        result = await db.execute(
            select(MarketAnalysis)
            .where(MarketAnalysis.user_id == user_id, MarketAnalysis.analysis_type == t)
            .order_by(desc(MarketAnalysis.created_at))
            .limit(1)
        )
        analysis = result.scalar_one_or_none()
        if analysis:
            results.append(analysis)
    return results
