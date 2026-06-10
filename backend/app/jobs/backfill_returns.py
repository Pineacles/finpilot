"""Nightly backfill job: fill in forward_return and alpha fields on signal_history rows.

Run via:
    docker compose exec -T api python -m app.jobs.backfill_returns

Or via systemd timer (see backfill-returns.timer).

Uses asyncpg directly (same driver as the main app) and httpx for Yahoo Finance
price fetches (same pattern as app/services/prices.py).
"""
import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backfill] %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# asyncpg wants a plain postgresql:// DSN (no driver suffix)
_raw_db_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://finpilot:finpilot_dev@localhost:5432/finpilot",
)
# Strip SQLAlchemy driver prefix so asyncpg.connect() is happy
DATABASE_DSN = (
    _raw_db_url
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgresql+psycopg2://", "postgresql://")
)

# Calendar day thresholds (conservative — better late than early)
THRESHOLDS = {
    "1d": 2,    # wait 2 calendar days for 1 trading day
    "5d": 8,    # wait 8 calendar days for 5 trading days
    "20d": 30,  # wait 30 calendar days for 20 trading days
}

BATCH_SIZE = 50

YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}

FAILURE_COUNT_FILE = "/tmp/backfill_failures.count"
ALERT_THRESHOLD = 3

# European ticker suffixes → use EU benchmark
EUROPEAN_SUFFIXES = (".L", ".SW", ".PA", ".DE", ".AS", ".MI", ".MC", ".BR")
EU_BENCHMARK = "EXSA.DE"    # iShares STOXX Europe 600 ETF on Xetra
US_BENCHMARK = "SPY"


# ---------------------------------------------------------------------------
# Yahoo Finance price fetch (async, matches prices.py pattern)
# ---------------------------------------------------------------------------

async def _fetch_yahoo_history(
    client: httpx.AsyncClient,
    symbol: str,
    period1: int,
    period2: int,
) -> list[dict]:
    """Fetch daily close prices from Yahoo Finance v8 chart API.

    Returns list of {"date": "YYYY-MM-DD", "close": float} sorted by date.
    """
    try:
        resp = await client.get(
            f"{YAHOO_BASE}/{symbol}",
            params={"interval": "1d", "period1": period1, "period2": period2},
            headers=YAHOO_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"Yahoo v8 returned {resp.status_code} for {symbol}")
            return []

        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            logger.warning(f"No chart result for {symbol}")
            return []

        result = result[0]
        timestamps = result.get("timestamp", [])
        closes = result["indicators"]["quote"][0].get("close", [])

        rows = []
        for ts, close in zip(timestamps, closes):
            if close is not None:
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append({"date": date_str, "close": close})
        return sorted(rows, key=lambda r: r["date"])

    except Exception as exc:
        logger.error(f"Yahoo fetch error for {symbol}: {exc}")
        return []


async def get_close_price(
    client: httpx.AsyncClient,
    symbol: str,
    target_date: datetime,
) -> Optional[float]:
    """Return the closing price for `symbol` on the nearest trading day >= target_date.

    Fetches a window from target_date-2d to target_date+7d to capture the right bar.
    """
    p1 = int((target_date - timedelta(days=2)).timestamp())
    p2 = int((target_date + timedelta(days=7)).timestamp())

    rows = await _fetch_yahoo_history(client, symbol, p1, p2)
    if not rows:
        return None

    target_str = target_date.strftime("%Y-%m-%d")

    # First trading day on or after target_date
    for row in rows:
        if row["date"] >= target_str:
            return row["close"]

    # Fallback: last available close before target (weekend/holiday edge case)
    before = [r for r in rows if r["date"] < target_str]
    if before:
        return before[-1]["close"]

    return None


# ---------------------------------------------------------------------------
# Benchmark selection
# ---------------------------------------------------------------------------

def pick_benchmark(symbol: Optional[str], benchmark_ticker: Optional[str]) -> Optional[str]:
    """Determine the benchmark ticker for alpha calculation."""
    if benchmark_ticker:
        return benchmark_ticker
    if symbol is None:
        return US_BENCHMARK  # market-wide tool, default to SPY
    for suffix in EUROPEAN_SUFFIXES:
        if symbol.upper().endswith(suffix.upper()):
            return EU_BENCHMARK
    return US_BENCHMARK


# ---------------------------------------------------------------------------
# Failure counter (plain file — no DB dependency)
# ---------------------------------------------------------------------------

def _read_failure_count() -> int:
    try:
        with open(FAILURE_COUNT_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _write_failure_count(count: int) -> None:
    try:
        with open(FAILURE_COUNT_FILE, "w") as f:
            f.write(str(count))
    except Exception as exc:
        logger.warning(f"Could not write failure count: {exc}")


def _handle_run_failed(reason: str) -> None:
    count = _read_failure_count() + 1
    _write_failure_count(count)
    logger.error(f"Backfill run failed: {reason} (consecutive failures: {count})")
    if count >= ALERT_THRESHOLD:
        logger.critical(
            "ALERT: Backfill has failed %d consecutive times. "
            "Manual intervention required. Last error: %s",
            count,
            reason,
        )
        # TODO: send alert via external notification integration when available


def _handle_run_success() -> None:
    _write_failure_count(0)


# ---------------------------------------------------------------------------
# Core async backfill logic
# ---------------------------------------------------------------------------

async def _process_horizon(
    conn: asyncpg.Connection,
    client: httpx.AsyncClient,
    horizon: str,
    cutoff: datetime,
    n_trading_days: int,
) -> tuple[int, int]:
    """Process one horizon (1d / 5d / 20d).  Returns (backfilled, failed)."""
    col_return = f"forward_return_{horizon}"
    col_alpha = f"alpha_{horizon}"

    rows = await conn.fetch(
        f"""
        SELECT id, symbol, benchmark_ticker, run_timestamp
        FROM signal_history
        WHERE {col_return} IS NULL
          AND run_timestamp < $1
        ORDER BY run_timestamp
        """,
        cutoff,
    )

    if not rows:
        logger.info(f"No rows pending for {horizon}")
        return 0, 0

    logger.info(f"Processing {len(rows)} rows for {horizon}")

    # Calendar days forward to find the Nth trading day close (rough approx)
    cal_days_forward = int(n_trading_days * 1.4) + 2

    batch: list[dict] = []
    failed = 0

    for row in rows:
        row_id = row["id"]
        symbol = row["symbol"]
        benchmark_ticker = row["benchmark_ticker"]
        run_ts: datetime = row["run_timestamp"]

        if run_ts.tzinfo is None:
            run_ts = run_ts.replace(tzinfo=timezone.utc)

        price_symbol = symbol if symbol else (benchmark_ticker or US_BENCHMARK)
        bench_symbol = pick_benchmark(symbol, benchmark_ticker)
        forward_date = run_ts + timedelta(days=cal_days_forward)

        # --- price at signal date ---
        price_at_run = await get_close_price(client, price_symbol, run_ts)
        if price_at_run is None:
            logger.warning(
                f"Row {row_id}: cannot fetch {price_symbol} at {run_ts.date()} — skipping"
            )
            failed += 1
            continue

        # --- price N trading days later ---
        price_later = await get_close_price(client, price_symbol, forward_date)
        if price_later is None:
            logger.warning(
                f"Row {row_id}: cannot fetch {price_symbol} forward price at {forward_date.date()} — skipping"
            )
            failed += 1
            continue

        forward_return = (price_later / price_at_run - 1) * 100

        # --- alpha ---
        alpha: Optional[float] = None
        if bench_symbol and bench_symbol != price_symbol:
            bench_at_run = await get_close_price(client, bench_symbol, run_ts)
            bench_later = await get_close_price(client, bench_symbol, forward_date)
            if bench_at_run and bench_later:
                bench_return = (bench_later / bench_at_run - 1) * 100
                alpha = forward_return - bench_return
            else:
                logger.warning(
                    f"Row {row_id}: cannot fetch benchmark {bench_symbol} prices — skipping alpha"
                )

        batch.append(
            {"id": row_id, "forward_return": forward_return, "alpha": alpha}
        )

        if len(batch) >= BATCH_SIZE:
            await _flush_batch(conn, batch, col_return, col_alpha)
            batch = []

    if batch:
        await _flush_batch(conn, batch, col_return, col_alpha)

    return len(rows) - failed, failed


async def _flush_batch(
    conn: asyncpg.Connection,
    batch: list[dict],
    col_return: str,
    col_alpha: str,
) -> None:
    """Write a batch of updates inside a single transaction."""
    async with conn.transaction():
        for item in batch:
            if item["alpha"] is not None:
                await conn.execute(
                    f"""
                    UPDATE signal_history
                    SET {col_return} = $1, {col_alpha} = $2
                    WHERE id = $3
                    """,
                    item["forward_return"],
                    item["alpha"],
                    item["id"],
                )
            else:
                await conn.execute(
                    f"""
                    UPDATE signal_history
                    SET {col_return} = $1
                    WHERE id = $2
                    """,
                    item["forward_return"],
                    item["id"],
                )
    logger.debug(f"Flushed batch of {len(batch)} rows for {col_return}")


async def run_backfill() -> None:
    logger.info("Starting forward-return backfill job")
    logger.info(f"Connecting to: {DATABASE_DSN}")

    now = datetime.now(timezone.utc)
    horizons = [
        ("1d",  now - timedelta(days=THRESHOLDS["1d"]),  1),
        ("5d",  now - timedelta(days=THRESHOLDS["5d"]),  5),
        ("20d", now - timedelta(days=THRESHOLDS["20d"]), 20),
    ]

    total_counts = {"1d": 0, "5d": 0, "20d": 0}
    total_failed = 0

    try:
        conn = await asyncpg.connect(DATABASE_DSN)
    except Exception as exc:
        _handle_run_failed(f"DB connect failed: {exc}")
        raise

    try:
        async with httpx.AsyncClient() as client:
            for horizon, cutoff, n_td in horizons:
                backfilled, failed = await _process_horizon(
                    conn, client, horizon, cutoff, n_td
                )
                total_counts[horizon] = backfilled
                total_failed += failed
    finally:
        await conn.close()

    total = sum(total_counts.values())
    logger.info(
        "Backfilled %d rows (1d: %d, 5d: %d, 20d: %d), failed: %d",
        total,
        total_counts["1d"],
        total_counts["5d"],
        total_counts["20d"],
        total_failed,
    )

    if total_failed > 0 and total == 0:
        _handle_run_failed(f"All {total_failed} eligible rows failed price lookup")
    else:
        _handle_run_success()
        if total_failed > 0:
            logger.warning(
                "%d rows skipped (price lookup failed) — will retry next run",
                total_failed,
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(run_backfill())
    except Exception as exc:
        _handle_run_failed(str(exc))
        logger.exception("Unhandled exception in backfill job")
        sys.exit(1)
