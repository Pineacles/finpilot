"""Viseca One transaction scraper.

Based on the API discovered by anothertobi/viseca-exporter:
- Auth: POST to login endpoint, get session cookie (AL_SESS-S)
- Transactions: GET /v1/card/{cardID}/transactions

For persistent auth, we use Playwright to handle the 2FA flow once,
then maintain the session cookie and refresh it before expiry.

Fallback: manual cookie injection via API endpoint.
"""
import json
from datetime import datetime, date, timezone

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.finance import Transaction, Category
from app.models.sync import SyncLog

# Session state
_viseca_session: dict = {"cookie": None, "card_id": None, "expires_at": 0}

# Default category mapping from Viseca PFM categories
VISECA_CATEGORY_MAP = {
    "Lebensmittel": "Groceries",
    "Restaurants": "Dining",
    "Transport": "Transport",
    "Gesundheit": "Health",
    "Unterhaltung": "Entertainment",
    "Shopping": "Shopping",
    "Reisen": "Travel",
    "Wohnen": "Housing",
    "Bildung": "Education",
    "Versicherungen": "Insurance",
    "Telekommunikation": "Telecom",
    "Bargeld": "Cash",
}


class VisecaClient:
    def __init__(self):
        self.api_url = settings.VISECA_API_URL
        self.client = httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        )

    def set_session(self, cookie: str, card_id: str):
        """Manually set session cookie and card ID."""
        _viseca_session["cookie"] = cookie
        _viseca_session["card_id"] = card_id

    async def _get_headers(self) -> dict:
        if not _viseca_session["cookie"]:
            raise RuntimeError(
                "No Viseca session. Use POST /api/sync/viseca/session to set cookie and card ID."
            )
        return {
            "Cookie": f"AL_SESS-S={_viseca_session['cookie']}",
            "Accept": "application/json",
        }

    async def get_cards(self) -> list[dict]:
        headers = await self._get_headers()
        resp = await self.client.get(f"{self.api_url}/card", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_transactions(
        self,
        card_id: str | None = None,
        page: int = 0,
        page_size: int = 50,
    ) -> list[dict]:
        headers = await self._get_headers()
        cid = card_id or _viseca_session["card_id"]
        if not cid:
            raise RuntimeError("No card ID set")

        resp = await self.client.get(
            f"{self.api_url}/card/{cid}/transactions",
            headers=headers,
            params={"page": page, "pagesize": page_size},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("transactions", data.get("data", []))

    async def close(self):
        await self.client.aclose()


viseca_client = VisecaClient()


async def ensure_categories(db: AsyncSession, user_id: str) -> dict[str, str]:
    """Ensure default categories exist. Returns name -> id mapping."""
    result = await db.execute(
        select(Category).where(Category.user_id == user_id)
    )
    existing = {c.name: c.id for c in result.scalars().all()}

    all_categories = set(VISECA_CATEGORY_MAP.values()) | {"Other", "Income", "Transfer"}
    for name in all_categories:
        if name not in existing:
            cat_type = "income" if name == "Income" else "transfer" if name == "Transfer" else "expense"
            cat = Category(user_id=user_id, name=name, type=cat_type)
            db.add(cat)
            await db.flush()
            existing[name] = cat.id

    return existing


def map_viseca_category(pfm_category_name: str | None) -> str:
    if not pfm_category_name:
        return "Other"
    return VISECA_CATEGORY_MAP.get(pfm_category_name, "Other")


async def sync_viseca_transactions(db: AsyncSession, user_id: str, account_id: str) -> int:
    """Sync transactions from Viseca One. Returns count of new records."""
    try:
        categories = await ensure_categories(db, user_id)

        synced = 0
        page = 0
        while True:
            transactions = await viseca_client.get_transactions(page=page)
            if not transactions:
                break

            for txn in transactions:
                txn_id = str(txn.get("transactionId", txn.get("id", "")))
                if not txn_id:
                    continue

                # Check dedup
                result = await db.execute(
                    select(Transaction).where(Transaction.viseca_transaction_id == txn_id)
                )
                if result.scalar_one_or_none():
                    continue

                # Parse transaction
                amount = txn.get("amount", txn.get("transactionAmount", 0))
                merchant = txn.get("merchantName", txn.get("merchant", "Unknown"))
                txn_date_str = txn.get("transactionDate", txn.get("date", ""))
                currency = txn.get("currency", "CHF")
                original_amount = txn.get("originalAmount")
                original_currency = txn.get("originalCurrency")
                pfm_category = txn.get("pfmCategoryName", txn.get("category", ""))

                # Parse date
                try:
                    if "T" in txn_date_str:
                        txn_date = datetime.fromisoformat(txn_date_str.replace("Z", "+00:00")).date()
                    else:
                        txn_date = date.fromisoformat(txn_date_str[:10])
                except (ValueError, TypeError):
                    txn_date = date.today()

                category_name = map_viseca_category(pfm_category)
                category_id = categories.get(category_name, categories.get("Other"))

                db.add(Transaction(
                    user_id=user_id,
                    account_id=account_id,
                    date=txn_date,
                    merchant=merchant,
                    amount=-abs(amount),  # Expenses are negative
                    original_amount=original_amount,
                    original_currency=original_currency,
                    currency=currency,
                    category_id=category_id,
                    viseca_transaction_id=txn_id,
                ))
                synced += 1

            if len(transactions) < 50:
                break
            page += 1

        db.add(SyncLog(
            user_id=user_id,
            source="viseca",
            status="success",
            records_synced=synced,
        ))
        await db.commit()
        return synced

    except Exception as e:
        db.add(SyncLog(
            user_id=user_id,
            source="viseca",
            status="failed",
            records_synced=0,
            error_message=str(e)[:500],
        ))
        await db.commit()
        raise
