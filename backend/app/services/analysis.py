"""AI-powered market analysis service.

Uses yfinance for market data and Claude for analysis generation.
Implements a multi-agent approach:
1. Data Agent — fetches relevant market data via yfinance
2. Analysis is run through Claude with specialized system prompts per analysis type
3. Results stored in DB for dashboard display
"""
import json
from datetime import datetime, timezone

import anthropic
import yfinance as yf
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.stock import StockPosition, MarketAnalysis


def _get_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


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
                # Basic technicals
                if len(hist) >= 50:
                    pos_data["sma_50"] = round(hist["Close"].rolling(50).mean().iloc[-1], 2)
                if len(hist) >= 20:
                    pos_data["sma_20"] = round(hist["Close"].rolling(20).mean().iloc[-1], 2)

                # Info
                info = ticker.info
                pos_data["sector"] = info.get("sector", "Unknown")
                pos_data["industry"] = info.get("industry", "Unknown")
                pos_data["pe_ratio"] = info.get("trailingPE")
                pos_data["market_cap"] = info.get("marketCap")
                pos_data["dividend_yield"] = info.get("dividendYield")
        except Exception:
            pos_data["price_history_30d"] = []

        data["positions"].append(pos_data)

    # Market overview (S&P 500)
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
    except Exception:
        pass

    # Treasury yields (^TNX = 10Y)
    try:
        tnx = yf.Ticker("^TNX")
        tnx_hist = tnx.history(period="5d")
        if not tnx_hist.empty:
            data["economic_indicators"]["us_10y_yield"] = round(tnx_hist["Close"].iloc[-1], 2)
    except Exception:
        pass

    # VIX
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        if not vix_hist.empty:
            data["economic_indicators"]["vix"] = round(vix_hist["Close"].iloc[-1], 2)
    except Exception:
        pass

    return data


def run_analysis(market_data: dict, analysis_type: str) -> dict:
    """Run multi-agent analysis using Claude."""
    client = _get_anthropic_client()

    system_prompts = {
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

    system = system_prompts.get(analysis_type, system_prompts["position"])

    user_msg = f"""Analyze this portfolio data:

{json.dumps(market_data, indent=2, default=str)}

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

    response = client.messages.create(
        model=settings.ANALYSIS_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
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
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = result.scalars().all()

    market_data = await fetch_market_data_for_positions(positions)
    analysis_content = run_analysis(market_data, analysis_type)

    analysis = MarketAnalysis(
        user_id=user_id,
        analysis_type=analysis_type,
        content=analysis_content,
        model_used=settings.ANALYSIS_MODEL,
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
