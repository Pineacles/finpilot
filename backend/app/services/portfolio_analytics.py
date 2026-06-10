"""Portfolio analytics — optimization, risk, attribution, FX impact.

Uses PyPortfolioOpt for mean-variance and risk-parity optimization.
All functions are async-compatible and work with the existing price service.
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def get_returns_matrix(symbols: list[str], days: int = 365) -> pd.DataFrame | None:
    """Fetch historical prices and compute daily returns matrix for given symbols."""
    from app.services.prices import get_history

    price_data: dict[str, list[float]] = {}
    dates: list[str] = []

    for sym in symbols:
        hist = await get_history(sym, range="1y" if days <= 365 else "2y", interval="1d")
        if not hist:
            continue
        price_data[sym] = [h["close"] for h in hist]
        if not dates:
            dates = [h["date"] for h in hist]

    if len(price_data) < 2:
        return None

    # Align to shortest series
    min_len = min(len(v) for v in price_data.values())
    df = pd.DataFrame({sym: vals[-min_len:] for sym, vals in price_data.items()})
    returns = df.pct_change().dropna()
    return returns


async def optimize_portfolio(
    symbols: list[str],
    current_weights: dict[str, float],
    total_value: float,
    l2_reg: float = 0.1,
    risk_free_rate: float = 0.01,
) -> dict:
    """Mean-variance optimization with L2 (ridge) regularization.

    Returns optimal weights, expected return, volatility, and Sharpe ratio.
    """
    from pypfopt import EfficientFrontier, expected_returns, risk_models

    returns = await get_returns_matrix(symbols)
    if returns is None or returns.empty:
        return {"error": "Insufficient price data for optimization"}

    try:
        mu = expected_returns.mean_historical_return(returns, frequency=252, compounding=True)
        S = risk_models.sample_cov(returns, frequency=252)

        ef = EfficientFrontier(mu, S)
        # L2 regularization (ridge penalty) to avoid extreme weights
        ef.add_objective(lambda w: l2_reg * np.sum(w ** 2))
        ef.max_sharpe(risk_free_rate=risk_free_rate)

        weights = ef.clean_weights()
        perf = ef.portfolio_performance(risk_free_rate=risk_free_rate)

        # Compute suggested allocation in CHF
        allocation = {sym: round(w * total_value, 2) for sym, w in weights.items() if w > 0.001}

        return {
            "weights": {sym: round(w, 4) for sym, w in weights.items() if w > 0.001},
            "allocation_chf": allocation,
            "expected_annual_return": round(perf[0] * 100, 2),
            "annual_volatility": round(perf[1] * 100, 2),
            "sharpe_ratio": round(perf[2], 3),
            "l2_regularization": l2_reg,
            "current_weights": current_weights,
        }
    except Exception as e:
        logger.error(f"Portfolio optimization failed: {e}")
        return {"error": str(e)}


async def risk_parity_weights(symbols: list[str]) -> dict:
    """Compute risk-parity (equal risk contribution) weights.

    Each position contributes equally to total portfolio risk.
    """
    from pypfopt import HRPOpt

    returns = await get_returns_matrix(symbols)
    if returns is None or returns.empty:
        return {"error": "Insufficient price data"}

    try:
        hrp = HRPOpt(returns)
        weights = hrp.optimize()
        weights = {sym: round(w, 4) for sym, w in weights.items() if w > 0.001}

        # Compute individual volatilities for context
        vols = returns.std() * np.sqrt(252) * 100
        individual_risk = {sym: round(float(vols.get(sym, 0)), 2) for sym in symbols if sym in vols.index}

        return {
            "weights": weights,
            "method": "hierarchical_risk_parity",
            "individual_volatility_pct": individual_risk,
        }
    except Exception as e:
        logger.error(f"Risk parity failed: {e}")
        return {"error": str(e)}


async def correlation_analysis(symbols: list[str], threshold: float = 0.7) -> dict:
    """Compute correlation matrix and flag highly correlated pairs."""
    returns = await get_returns_matrix(symbols)
    if returns is None or returns.empty:
        return {"error": "Insufficient price data"}

    corr = returns.corr()

    # Find pairs above threshold
    high_corr_pairs = []
    for i, sym1 in enumerate(corr.columns):
        for j, sym2 in enumerate(corr.columns):
            if i < j:
                c = float(corr.iloc[i, j])
                if abs(c) >= threshold:
                    high_corr_pairs.append({
                        "pair": [sym1, sym2],
                        "correlation": round(c, 3),
                        "risk": "high" if abs(c) >= 0.85 else "moderate",
                    })

    # Full matrix as dict
    matrix = {}
    for sym in corr.columns:
        matrix[sym] = {s: round(float(corr.loc[sym, s]), 3) for s in corr.columns}

    return {
        "matrix": matrix,
        "high_correlation_pairs": sorted(high_corr_pairs, key=lambda x: -abs(x["correlation"])),
        "threshold": threshold,
        "symbols": list(corr.columns),
    }


async def performance_attribution(
    positions: list[dict],
    benchmark: str = "SPY",
    days: int = 252,
) -> dict:
    """Alpha/beta decomposition for each position vs a benchmark.

    positions: [{"symbol": "AAPL", "weight": 0.3, "pnl_pct": 15.2}, ...]
    """
    from app.services.prices import get_history

    # Get benchmark returns
    bench_hist = await get_history(benchmark, range="1y", interval="1d")
    if not bench_hist:
        return {"error": f"Could not fetch benchmark {benchmark}"}

    bench_prices = [h["close"] for h in bench_hist]
    bench_returns = pd.Series(bench_prices).pct_change().dropna()

    results = []
    portfolio_alpha = 0.0
    portfolio_beta = 0.0

    for pos in positions:
        sym = pos["symbol"]
        hist = await get_history(sym, range="1y", interval="1d")
        if not hist:
            results.append({"symbol": sym, "error": "no data"})
            continue

        stock_prices = [h["close"] for h in hist]
        stock_returns = pd.Series(stock_prices).pct_change().dropna()

        # Align lengths
        min_len = min(len(stock_returns), len(bench_returns))
        sr = stock_returns.iloc[-min_len:].values
        br = bench_returns.iloc[-min_len:].values

        # Beta = cov(stock, bench) / var(bench)
        cov = np.cov(sr, br)
        beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else 0

        # Annualized returns
        stock_annual = float((1 + sr.mean()) ** 252 - 1) * 100
        bench_annual = float((1 + br.mean()) ** 252 - 1) * 100

        # Alpha = stock_return - beta * bench_return (annualized)
        alpha = stock_annual - beta * bench_annual

        weight = pos.get("weight", 0)
        portfolio_alpha += alpha * weight
        portfolio_beta += beta * weight

        results.append({
            "symbol": sym,
            "beta": round(beta, 3),
            "alpha_pct": round(alpha, 2),
            "annual_return_pct": round(stock_annual, 2),
            "volatility_pct": round(float(sr.std() * np.sqrt(252) * 100), 2),
            "weight": round(weight, 4),
        })

    return {
        "benchmark": benchmark,
        "positions": results,
        "portfolio_alpha_pct": round(portfolio_alpha, 2),
        "portfolio_beta": round(portfolio_beta, 3),
        "benchmark_annual_return_pct": round(float((1 + bench_returns.mean()) ** 252 - 1) * 100, 2),
    }


async def fx_impact_analysis(positions: list[dict], base_currency: str = "CHF") -> dict:
    """Compute FX-adjusted P&L showing currency drag/benefit.

    For each non-CHF position, shows raw P&L vs FX-adjusted P&L
    and the carry penalty from USD/CHF movement.
    """
    from app.services.prices import get_fx_rate, get_history

    results = []
    total_fx_impact = 0.0

    for pos in positions:
        sym = pos["symbol"]
        ccy = pos.get("currency", "USD")

        if ccy == base_currency:
            results.append({
                "symbol": sym,
                "currency": ccy,
                "fx_impact_pct": 0.0,
                "fx_impact_chf": 0.0,
                "note": "same currency as base",
            })
            continue

        # Current FX rate
        current_fx = await get_fx_rate(ccy, base_currency)

        # Get historical FX rate (approximate from a year ago)
        pair = f"{ccy}{base_currency}=X"
        fx_hist = await get_history(pair, range="1y", interval="1d")

        if fx_hist and len(fx_hist) > 10:
            # FX at entry (approximate: use rate from when position was opened)
            entry_fx = fx_hist[0]["close"]
            fx_change_pct = ((current_fx - entry_fx) / entry_fx) * 100

            market_value = pos.get("market_value", 0)
            fx_impact_chf = market_value * (fx_change_pct / 100)
        else:
            fx_change_pct = 0
            fx_impact_chf = 0

        total_fx_impact += fx_impact_chf

        results.append({
            "symbol": sym,
            "currency": ccy,
            "current_fx_rate": round(current_fx, 4),
            "fx_change_pct": round(fx_change_pct, 2),
            "fx_impact_chf": round(fx_impact_chf, 2),
            "market_value_chf": round(pos.get("market_value", 0), 2),
        })

    return {
        "base_currency": base_currency,
        "positions": results,
        "total_fx_impact_chf": round(total_fx_impact, 2),
        "note": "Negative = CHF strengthened (hurts USD positions). Positive = CHF weakened (helps).",
    }


def check_price_collar(submitted_price: float, market_price: float, collar_pct: float = 5.0) -> dict:
    """Check if a submitted trade price is within the price collar.

    Returns pass/fail and the deviation percentage.
    """
    if market_price <= 0:
        return {"pass": True, "reason": "no market price available"}

    deviation_pct = abs(submitted_price - market_price) / market_price * 100

    return {
        "pass": deviation_pct <= collar_pct,
        "submitted_price": submitted_price,
        "market_price": round(market_price, 2),
        "deviation_pct": round(deviation_pct, 2),
        "collar_pct": collar_pct,
        "reason": f"Price deviation {deviation_pct:.1f}% {'within' if deviation_pct <= collar_pct else 'exceeds'} {collar_pct}% collar",
    }


async def earnings_calendar(symbols: list[str]) -> list[dict]:
    """Fetch next earnings dates for given symbols from Yahoo Finance."""
    import httpx

    results = []
    for sym in symbols:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"interval": "1d", "range": "1d"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code != 200:
                    continue

                meta = resp.json()["chart"]["result"][0]["meta"]
                # earningsTimestamp is in epoch seconds (if available)
                earn_ts = meta.get("earningsTimestamp") or meta.get("earningsTimestampStart")
                if earn_ts:
                    earn_date = datetime.fromtimestamp(earn_ts).date()
                    results.append({
                        "symbol": sym,
                        "earnings_date": earn_date.isoformat(),
                        "days_until": (earn_date - datetime.now().date()).days,
                    })
                else:
                    results.append({"symbol": sym, "earnings_date": None, "days_until": None})
        except Exception as e:
            logger.warning(f"Earnings fetch failed for {sym}: {e}")
            results.append({"symbol": sym, "earnings_date": None, "days_until": None})

    return sorted(
        [r for r in results if r["earnings_date"]],
        key=lambda x: x["days_until"] if x["days_until"] is not None else 999,
    ) + [r for r in results if not r["earnings_date"]]
