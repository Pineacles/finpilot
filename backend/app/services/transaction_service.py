"""Business logic for transactions and categories.

Shared between the JWT-authenticated dashboard router (transactions.py) and
the API-key agent router (agent_finance_router.py) so the two surfaces can't
drift out of sync. Routers stay thin: parse/validate the request, call into
this module, shape the response.
"""
from datetime import date

from sqlalchemy import select, desc, and_, delete as sa_delete
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Transaction, Category
from app.models.merchant import Merchant
from app.schemas.finance import TransactionCreate, TransactionResponse, TransactionUpdate


class TransactionNotFoundError(Exception):
    """Raised when a transaction_id doesn't exist (or isn't owned by the user)."""

    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        super().__init__(f"Transaction not found: {transaction_id}")


async def list_transactions(
    db: AsyncSession,
    user_id: str,
    *,
    category_id: str | None = None,
    category_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TransactionResponse]:
    """List transactions for a user, with optional filters.

    `category_id` (exact id match) and `category_name` (join on Category.name)
    are both supported since the dashboard surface filters by id and the agent
    surface filters by human-readable category name.
    """
    ParentCat = aliased(Category)
    query = (
        select(Transaction, Category, ParentCat)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .outerjoin(ParentCat, Category.parent_id == ParentCat.id)
        .where(Transaction.user_id == user_id)
    )
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if category_name:
        query = query.where(Category.name == category_name)
    if from_date:
        query = query.where(Transaction.date >= from_date)
    if to_date:
        query = query.where(Transaction.date <= to_date)
    if search:
        query = query.where(Transaction.merchant.ilike(f"%{search}%"))

    query = query.order_by(desc(Transaction.date)).limit(limit).offset(offset)
    result = await db.execute(query)

    responses = []
    for txn, cat, parent_cat in result.all():
        r = TransactionResponse.model_validate(txn)
        r.category_name = cat.name if cat else None
        r.parent_category_name = parent_cat.name if parent_cat else None
        responses.append(r)
    return responses


async def create_transaction(db: AsyncSession, user_id: str, body: TransactionCreate) -> TransactionResponse:
    txn = Transaction(user_id=user_id, **body.model_dump())
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


async def update_transaction(
    db: AsyncSession, user_id: str, transaction_id: str, body: TransactionUpdate
) -> TransactionResponse:
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.user_id == user_id)
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise TransactionNotFoundError(transaction_id)

    old_merchant = txn.merchant
    old_category_id = txn.category_id

    # Only apply actual data fields to the transaction (not control flags)
    for field in ("category_id", "notes", "merchant"):
        value = getattr(body, field, None)
        if value is not None:
            setattr(txn, field, value)

    merchant_changed = body.merchant and body.merchant != old_merchant
    category_changed = body.category_id and body.category_id != old_category_id

    # Build conditions for finding related transactions
    should_bulk_merchant = merchant_changed and body.apply_merchant_to_all
    should_bulk_category = category_changed and body.apply_category_to_all

    if should_bulk_merchant or should_bulk_category:
        conditions = [
            Transaction.user_id == user_id,
            Transaction.merchant == old_merchant,
            Transaction.id != transaction_id,
        ]
        # Scope by description if provided (e.g. only "carvolution" notes, not all "revolut")
        if body.description_filter:
            conditions.append(Transaction.notes.ilike(f"%{body.description_filter}%"))

        others = await db.execute(select(Transaction).where(and_(*conditions)))
        for other in others.scalars().all():
            if should_bulk_merchant:
                other.merchant = body.merchant
            if should_bulk_category:
                other.category_id = body.category_id

    # Upsert Merchant DB rule so future imports auto-categorize correctly
    final_merchant = body.merchant or old_merchant
    final_category = body.category_id or old_category_id
    if final_merchant and final_merchant != "Pending" and final_category:
        # Include description_filter as a pattern so future imports with that keyword also match
        await upsert_merchant_rule(
            db, user_id, final_merchant,
            old_merchant if merchant_changed else None,
            final_category,
            extra_pattern=body.description_filter,
        )

    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


async def delete_transaction(db: AsyncSession, user_id: str, transaction_id: str) -> None:
    """Delete a single transaction. Scoped to the owning user."""
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.user_id == user_id)
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise TransactionNotFoundError(transaction_id)
    await db.delete(txn)
    await db.commit()


async def bulk_delete_transactions(db: AsyncSession, user_id: str, transaction_ids: list[str]) -> int:
    """Delete every transaction id in the list that belongs to user_id.

    IDs that don't exist or belong to another user are silently ignored (no
    error) — returns the number of rows actually deleted.
    """
    if not transaction_ids:
        return 0
    result = await db.execute(
        sa_delete(Transaction).where(
            and_(Transaction.user_id == user_id, Transaction.id.in_(transaction_ids))
        )
    )
    await db.commit()
    return result.rowcount or 0


async def upsert_merchant_rule(
    db: AsyncSession,
    user_id: str,
    merchant_name: str,
    original_name: str | None,
    category_id: str,
    extra_pattern: str | None = None,
) -> None:
    """Create or update a Merchant DB entry so future imports auto-categorize.

    Builds patterns from both the new merchant name and the original name
    (plus an optional extra pattern, e.g. a description-filter keyword).
    Always scoped to `user_id` — a previous copy of this helper (in the agent
    router) queried Merchant by name only, which could match another user's
    rule; that bug is fixed by consolidating on this implementation.
    """
    patterns_set: set[str] = set()
    for name in (merchant_name, original_name):
        if name:
            cleaned = name.strip().lower()
            if cleaned:
                patterns_set.add(cleaned)
                for word in cleaned.split():
                    if len(word) >= 4 and word not in ("gmbh", "sarl", "bank", "card", "payment", "services"):
                        patterns_set.add(word)
    if extra_pattern:
        cleaned = extra_pattern.strip().lower()
        if cleaned:
            patterns_set.add(cleaned)

    if not patterns_set:
        return

    result = await db.execute(
        select(Merchant).where(and_(Merchant.name == merchant_name, Merchant.user_id == user_id))
    )
    existing = result.scalar_one_or_none()

    if existing:
        old_patterns = set(p.strip().lower() for p in existing.patterns.split("|") if p.strip())
        merged = old_patterns | patterns_set
        existing.patterns = "|".join(sorted(merged))
        existing.default_category_id = category_id
    else:
        db.add(Merchant(
            user_id=user_id,
            name=merchant_name,
            patterns="|".join(sorted(patterns_set)),
            default_category_id=category_id,
            is_system=False,
        ))


async def list_categories(db: AsyncSession, user_id: str) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.user_id == user_id).order_by(Category.name)
    )
    return list(result.scalars().all())


async def create_category(db: AsyncSession, user_id: str, body) -> Category:
    cat = Category(user_id=user_id, **body.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat
