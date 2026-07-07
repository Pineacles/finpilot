"""Export the AI stock-analysis / AI-trading tables to a JSON file before dropping them.

The AI analysis stack (market analyses, post-mortems, buy assessments, pending
orders, signal history, tool weights, tool weight proposals) was removed from
the product — the approach was tried in production and didn't work (see the
project README). The `f3a8c91b5d2e_drop_ai_analysis_tables` migration drops
the underlying tables outright. Run this script first if you want a copy of
the data for your own records; it does not touch the database.

Usage:
    cd backend
    python scripts/export_ai_archive.py [output_path.json]

Connects using the same DATABASE_URL the app uses (env var or backend/.env).
If output_path is omitted, writes to ./ai_archive_<timestamp>.json in the
current directory.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import text

# Run from backend/ (or with backend/ on PYTHONPATH) so `app.*` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import engine  # noqa: E402  (import after sys.path tweak)

# Order doesn't matter for a read-only dump, but keep it FK-child-first for readability.
TABLES = [
    "pending_orders",
    "post_mortems",
    "buy_assessments",
    "signal_history",
    "tool_weight_proposals",
    "tool_weights",
    "market_analyses",
]


def _json_default(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


async def export_table(conn, table: str) -> list[dict]:
    try:
        result = await conn.execute(text(f"SELECT * FROM {table}"))
    except Exception as exc:
        print(f"  {table}: skipped ({exc})")
        return []
    rows = [dict(row._mapping) for row in result.fetchall()]
    print(f"  {table}: {len(rows)} row(s)")
    return rows


async def main(output_path: Path) -> None:
    archive: dict = {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tables": {},
    }

    print(f"Connecting via {engine.url.render_as_string(hide_password=True)}")
    async with engine.connect() as conn:
        for table in TABLES:
            archive["tables"][table] = await export_table(conn, table)
    await engine.dispose()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(archive, indent=2, default=_json_default))

    total_rows = sum(len(rows) for rows in archive["tables"].values())
    print(f"\nWrote {total_rows} total row(s) across {len(TABLES)} tables to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    else:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path(f"ai_archive_{stamp}.json")

    asyncio.run(main(out))
