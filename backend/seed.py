"""Seed script: creates a default user with API key.

Credentials are read from environment variables:
  SEED_EMAIL    : defaults to admin@example.com
  SEED_PASSWORD : defaults to change-me (change before use!)

Optional --demo flag additionally generates ~6 months of plausible but
entirely FAKE Swiss personal-finance data, so the app's features are visible
without needing a real bank export:

  - salary, rent, health insurance, an SBB travelcard, groceries (Migros/Coop)
  - a Migros Cumulus (Cembra) credit-card cycle with monthly auto-settlement
    (card purchases each month + a bank-side payment that zeroes the card via
    services/settlement.py, the same code path a real import would trigger)
  - a small ETF/stock portfolio (VWRL, CHSPI, AAPL, Novartis) with trades
  - budgets, a savings goal, recurring expenses, and watchlist entries

Generation is deterministic (fixed RNG seed, fixed fake calendar window) so
running it twice against a fresh database produces byte-identical data. No
real names, account numbers, or figures: everything here is synthetic.

    python seed.py            # just the user + starter accounts
    python seed.py --demo     # ...plus the fake demo dataset above
"""
import argparse
import asyncio
import os
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, engine, Base
from app.core.security import hash_password, generate_api_key
from app.models.account import Account
from app.models.finance import Budget, Category, RecurringExpense, SavingsGoal
from app.models.stock import StockPosition, StockTransaction, SymbolClassification
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants

SEED_EMAIL = os.environ.get("SEED_EMAIL", "admin@example.com")
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "change-me")

# Fixed fake calendar window for --demo data. Deliberately NOT "today minus 6
# months": the data is synthetic, so pinning it to a fixed window keeps the
# generated dataset identical across runs regardless of when seed.py executes.
DEMO_MONTHS = [(2026, m) for m in range(1, 7)]  # Jan..Jun 2026
DEMO_RNG_SEED = 20260107


async def seed(demo: bool = False):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == SEED_EMAIL))
        if result.scalar_one_or_none():
            print("Seed user already exists, skipping.")
            return

        api_key = generate_api_key()
        user = User(
            email=SEED_EMAIL,
            password_hash=hash_password(SEED_PASSWORD),
            api_key=api_key,
            display_name="Admin",
            base_currency="CHF",
        )
        db.add(user)
        await db.flush()

        # Create default accounts
        accounts = [
            Account(user_id=user.id, name="Saxo Bank", type="brokerage", currency="CHF"),
            Account(user_id=user.id, name="Viseca One", type="credit_card", currency="CHF"),
        ]
        db.add_all(accounts)
        await db.commit()

        print(f"Seed user created: {SEED_EMAIL}")
        print(f"API Key: {api_key}")

        if demo:
            await seed_demo_data(db, user)
            print("Demo data generated: 6 months of fake Swiss transactions, "
                  "a Cumulus settlement cycle, a small ETF/stock portfolio, "
                  "budgets, a savings goal, recurring expenses, and a watchlist.")


# ── Demo data ─────────────────────────────────────────────────────────

async def _category_ids(db: AsyncSession, user_id: str) -> dict[str, str]:
    result = await db.execute(select(Category).where(Category.user_id == user_id))
    return {c.name: c.id for c in result.scalars().all()}


async def _get_or_create_account(db: AsyncSession, user_id: str, name: str, type_: str, currency: str = "CHF") -> Account:
    result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.name == name)
    )
    account = result.scalar_one_or_none()
    if account:
        return account
    account = Account(user_id=user_id, name=name, type=type_, currency=currency)
    db.add(account)
    await db.flush()
    return account


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    return start, end


async def seed_demo_data(db: AsyncSession, user: User) -> None:
    """Populate ~6 fake months of Swiss personal-finance activity for `user`.

    Deterministic: seeded RNG + a fixed fake calendar window (DEMO_MONTHS).
    """
    rng = random.Random(DEMO_RNG_SEED)
    user_id = user.id

    await seed_merchants(db, user_id)
    await db.commit()
    cat_ids = await _category_ids(db, user_id)

    bank = await _get_or_create_account(db, user_id, "Valiant Bank", "bank")
    card = await _get_or_create_account(db, user_id, "Cumulus Card", "credit_card")
    result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.type == "brokerage")
    )
    brokerage = result.scalars().first() or await _get_or_create_account(db, user_id, "Saxo Bank", "brokerage")

    # The base seed() flow also creates a "Viseca One" credit_card account.
    # services/settlement.py matches the bank-side payment against the FIRST
    # credit_card account whose settlement_patterns match, and with two cards
    # both left on the default pattern list (cembra/cumulus/viseca...), the
    # always-empty Viseca account would shadow the real Cumulus Card match
    # every month (matched first, balance already 0 -> "skipped", and the
    # loop never falls through to try the Cumulus Card). Pin Viseca to a
    # pattern that can never appear in our demo bank statements so the
    # Cumulus settlement unambiguously targets the Cumulus Card.
    other_cards = (await db.execute(
        select(Account).where(
            Account.user_id == user_id, Account.type == "credit_card", Account.name != "Cumulus Card",
        )
    )).scalars().all()
    for other in other_cards:
        other.settlement_patterns = ["viseca-one-manual-repayment-not-used-in-demo"]

    await db.commit()

    grocery_stores = ["Migros", "Coop"]
    dining_spots = ["Starbucks", "McDonald's", "JustEat"]
    shopping_spots = ["Zalando", "Galaxus"]

    for i, (year, month) in enumerate(DEMO_MONTHS):
        _, month_end = _month_range(year, month)

        # ── Credit card: everyday purchases ──────────────────────────
        card_txns: list[dict] = []
        ref_base = f"demo-card-{year}{month:02d}"

        # Groceries: 6-9 purchases through the month
        for j in range(rng.randint(6, 9)):
            store = rng.choice(grocery_stores)
            day = rng.randint(1, 28)
            amount = -round(rng.uniform(12, 95), 2)
            card_txns.append({
                "date": date(year, month, day),
                "description": f"Kartenzahlung {store} Filiale",
                "merchant": store, "counterparty": store,
                "amount": amount, "currency": "CHF",
                "payment_type": "CCRD", "reference": f"{ref_base}-groc-{j}",
            })

        # Dining: 2-3 purchases
        for j in range(rng.randint(2, 3)):
            spot = rng.choice(dining_spots)
            day = rng.randint(1, 28)
            amount = -round(rng.uniform(8, 45), 2)
            card_txns.append({
                "date": date(year, month, day),
                "description": f"Kartenzahlung {spot}",
                "merchant": spot, "counterparty": spot,
                "amount": amount, "currency": "CHF",
                "payment_type": "CCRD", "reference": f"{ref_base}-dine-{j}",
            })

        # Subscriptions: Netflix + Spotify, fixed small amounts, every month
        card_txns.append({
            "date": date(year, month, 5), "description": "Kartenzahlung Netflix.com",
            "merchant": "Netflix", "counterparty": "Netflix",
            "amount": -15.90, "currency": "CHF",
            "payment_type": "CCRD", "reference": f"{ref_base}-netflix",
        })
        card_txns.append({
            "date": date(year, month, 7), "description": "Kartenzahlung Spotify AB",
            "merchant": "Spotify", "counterparty": "Spotify",
            "amount": -12.95, "currency": "CHF",
            "payment_type": "CCRD", "reference": f"{ref_base}-spotify",
        })

        # Occasional online shopping (~1 in 3 months)
        if rng.random() < 0.35:
            shop = rng.choice(shopping_spots)
            day = rng.randint(1, 28)
            amount = -round(rng.uniform(40, 220), 2)
            card_txns.append({
                "date": date(year, month, day),
                "description": f"Kartenzahlung {shop}",
                "merchant": shop, "counterparty": shop,
                "amount": amount, "currency": "CHF",
                "payment_type": "CCRD", "reference": f"{ref_base}-shop",
            })

        await import_transactions(
            db, user_id, card.id, "", use_ai=False,
            pre_parsed=card_txns, source_format="demo",
        )

        # ── Bank: salary, rent, insurance, SBB, TWINT, card settlement ──
        card_total = round(sum(abs(t["amount"]) for t in card_txns), 2)
        bank_txns: list[dict] = [
            {
                "date": date(year, month, 25), "description": "Lohnzahlung Helvetia Software AG",
                "merchant": "Helvetia Software AG", "counterparty": "Helvetia Software AG",
                "amount": round(8200 + rng.uniform(-50, 50), 2), "currency": "CHF",
                "payment_type": "RCDT", "reference": f"demo-bank-{year}{month:02d}-salary",
            },
            {
                "date": date(year, month, 1), "description": "Miete Wohnung",
                "merchant": "Immo Verwaltung AG", "counterparty": "Immo Verwaltung AG",
                "amount": -1450.00, "currency": "CHF",
                "payment_type": "ICDT", "reference": f"demo-bank-{year}{month:02d}-rent",
            },
            {
                "date": date(year, month, 20), "description": "CSS Kranken Praemie",
                "merchant": "CSS Versicherung", "counterparty": "CSS Versicherung",
                "amount": -389.40, "currency": "CHF",
                "payment_type": "ICDT", "reference": f"demo-bank-{year}{month:02d}-insurance",
            },
            {
                "date": date(year, month, 3), "description": "Dauerauftrag SBB Generalabonnement",
                "merchant": "SBB CFF FFS", "counterparty": "SBB CFF FFS",
                "amount": -79.00, "currency": "CHF",
                "payment_type": "ICDT", "reference": f"demo-bank-{year}{month:02d}-sbb",
            },
            {
                "date": date(year, month, 15), "description": "TWINT Belastung Alex M",
                "merchant": "Alex M", "counterparty": "",
                "amount": -round(rng.uniform(10, 60), 2), "currency": "CHF",
                "payment_type": "", "reference": f"demo-bank-{year}{month:02d}-twint",
            },
            {
                # Cumulus settlement: merchant matches settlement.DEFAULT_SETTLEMENT_PATTERNS
                # ("cembra"/"cumulus"), so importing this triggers the card
                # auto-reset to CHF 0 via services/settlement.py.
                "date": date(year, month, 28), "description": "Kreditkartenabrechnung Cumulus",
                "merchant": "Cembra Money Bank AG", "counterparty": "Cembra Money Bank AG",
                "amount": -card_total, "currency": "CHF",
                "payment_type": "ICDT", "reference": f"demo-bank-{year}{month:02d}-cumulus",
            },
        ]

        await import_transactions(
            db, user_id, bank.id, "", use_ai=False,
            pre_parsed=bank_txns, source_format="demo",
        )

    # ── Small ETF/stock portfolio (fixed fake prices, no network calls) ──
    stock_defs = [
        {
            "symbol": "VWRL", "name": "Vanguard FTSE All-World UCITS ETF", "currency": "CHF",
            "asset_type": "etf", "last_price": 112.40,
            "buys": [(date(2026, 1, 10), 20, 102.50, 5.0), (date(2026, 4, 14), 20, 107.80, 5.0)],
        },
        {
            "symbol": "CHSPI", "name": "iShares Core SPI ETF (CH)", "currency": "CHF",
            "asset_type": "etf", "last_price": 126.90,
            "buys": [(date(2026, 2, 5), 15, 118.40, 5.0), (date(2026, 5, 6), 10, 123.10, 5.0)],
        },
        {
            "symbol": "AAPL", "name": "Apple Inc.", "currency": "USD",
            "last_price": 192.75,
            "buys": [(date(2026, 1, 20), 10, 160.20, 8.0), (date(2026, 3, 18), 5, 178.50, 8.0)],
        },
        {
            "symbol": "NOVN.SW", "name": "Novartis AG", "currency": "CHF",
            "last_price": 91.20,
            "buys": [(date(2026, 2, 25), 20, 84.60, 10.0)],
        },
    ]
    for spec in stock_defs:
        total_qty = sum(b[1] for b in spec["buys"])
        avg_cost = sum(b[1] * b[2] for b in spec["buys"]) / total_qty
        for trade_date, qty, price, fees in spec["buys"]:
            db.add(StockTransaction(
                user_id=user_id, account_id=brokerage.id,
                symbol=spec["symbol"], type="buy", quantity=qty, price=price,
                fees=fees, currency=spec["currency"],
                executed_at=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc),
            ))
        db.add(StockPosition(
            user_id=user_id, account_id=brokerage.id,
            symbol=spec["symbol"], name=spec["name"],
            quantity=total_qty, avg_cost_price=round(avg_cost, 2),
            currency=spec["currency"], last_price=spec["last_price"],
            last_price_at=datetime.now(timezone.utc),
        ))
        db.add(SymbolClassification(
            user_id=user_id, symbol=spec["symbol"],
            asset_type=spec.get("asset_type", "equity"), source="user",
        ))

    # ── Watchlist: tracked but not held, no analysis/recommendations ──
    for symbol in ["NVDA", "TSLA", "MSFT", "SMI"]:
        db.add(WatchlistItem(user_id=user_id, symbol=symbol))

    # ── Budgets (monthly caps on a few expense categories) ──────────
    for name, cat_name, amount in [
        ("Groceries", "Groceries", 600.0),
        ("Dining", "Dining", 300.0),
        ("Entertainment", "Entertainment", 150.0),
    ]:
        db.add(Budget(
            user_id=user_id, name=name, category_id=cat_ids.get(cat_name),
            amount=amount, period="monthly", start_date=date(2026, 1, 1),
        ))

    # ── Savings goal ──────────────────────────────────────────────
    db.add(SavingsGoal(
        user_id=user_id, name="Emergency Fund",
        target_amount=15000.0, current_amount=6400.0,
        target_date=date(2026, 12, 31), currency="CHF",
    ))

    # ── Recurring expenses (the confirmed/tracked list, distinct from the
    # auto-detection suggestions: as if the user had already confirmed
    # these from the transaction history generated above) ──────────
    for name, cat_name, amount, day, freq in [
        ("Rent", "Rent", 1450.0, 1, "monthly"),
        ("CSS Health Insurance", "Insurance", 389.40, 20, "monthly"),
        ("SBB Generalabonnement", "Public Transport", 79.00, 3, "monthly"),
        ("Netflix", "Subscriptions", 15.90, 5, "monthly"),
        ("Spotify", "Subscriptions", 12.95, 7, "monthly"),
    ]:
        db.add(RecurringExpense(
            user_id=user_id, name=name, amount=amount, currency="CHF",
            frequency=freq, next_due_date=date(2026, 7, day),
            category_id=cat_ids.get(cat_name),
        ))

    await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FinPilot with a user (and optionally fake demo data).")
    parser.add_argument("--demo", action="store_true", help="Also generate ~6 months of deterministic fake demo data.")
    args = parser.parse_args()
    asyncio.run(seed(demo=args.demo))
