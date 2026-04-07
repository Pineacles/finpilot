"""Seed Swiss merchant database."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.models.finance import Category

# merchant_name: (patterns pipe-separated, category_name)
SWISS_MERCHANTS = {
    "Migros": ("migros", "Groceries"),
    "Coop": ("coop-|coop ", "Groceries"),
    "Denner": ("denner", "Groceries"),
    "Aldi": ("aldi", "Groceries"),
    "Lidl": ("lidl", "Groceries"),
    "Volg": ("volg", "Groceries"),
    "Spar": ("spar ", "Groceries"),
    "Manor": ("manor", "Shopping"),
    "Jumbo": ("jumbo", "Shopping"),
    "IKEA": ("ikea", "Shopping"),
    "Galaxus": ("galaxus|digitec", "Shopping"),
    "Zalando": ("zalando", "Shopping"),
    "Amazon": ("amazon|amzn", "Shopping"),
    "SBB": ("sbb|schweizerische bundesbahnen", "Transport"),
    "BLS": ("bls ", "Transport"),
    "ZVV": ("zvv", "Transport"),
    "AGROLA": ("agrola", "Transport"),
    "Shell": ("shell", "Transport"),
    "BP": ("bp ", "Transport"),
    "Parkingpay": ("parkingpay", "Transport"),
    "Swisscom": ("swisscom", "Telecom"),
    "Sunrise": ("sunrise", "Telecom"),
    "Salt": ("salt mobile", "Telecom"),
    "Netflix": ("netflix", "Entertainment"),
    "Spotify": ("spotify", "Entertainment"),
    "YouTube": ("youtube|google youtube", "Entertainment"),
    "Disney+": ("disney", "Entertainment"),
    "Apple": ("apple.com|apple store", "Entertainment"),
    "Google One": ("google one", "Entertainment"),
    "Steam": ("steam", "Entertainment"),
    "Patreon": ("patreon", "Entertainment"),
    "Claude AI": ("claude.ai", "Entertainment"),
    "McDonald's": ("mcdonald", "Dining"),
    "Burger King": ("burger king", "Dining"),
    "Starbucks": ("starbucks", "Dining"),
    "JustEat": ("justeat|just eat|eat.ch", "Dining"),
    "Uber Eats": ("uber eats", "Dining"),
    "CSS": ("css versicherung|css kranken", "Insurance"),
    "Helsana": ("helsana", "Insurance"),
    "Visana": ("visana", "Insurance"),
    "Concordia": ("concordia", "Insurance"),
    "Mobiliar": ("mobiliar", "Insurance"),
    "AXA": ("axa ", "Insurance"),
    "Zurich": ("zurich versicherung", "Insurance"),
    "Cembra": ("cembra", "Insurance"),
    "PostFinance": ("postfinance", "Transfer"),
    "PayPal": ("paypal", "Shopping"),
    "TWINT": ("twint", "Other"),
}


async def seed_merchants(db: AsyncSession, user_id: str):
    """Seed merchant database and ensure categories exist."""
    # Ensure all needed categories exist
    needed_cats = set(cat for _, cat in SWISS_MERCHANTS.values())
    needed_cats |= {"Salary", "Rent", "Cash", "Income", "Transfer", "Other", "Health", "Education"}

    existing = {}
    result = await db.execute(select(Category).where(Category.user_id == user_id))
    for c in result.scalars().all():
        existing[c.name] = c.id

    for name in needed_cats:
        if name not in existing:
            cat_type = "income" if name in ("Salary", "Income") else "transfer" if name == "Transfer" else "expense"
            cat = Category(user_id=user_id, name=name, type=cat_type)
            db.add(cat)
            await db.flush()
            existing[name] = cat.id

    # Seed merchants
    result = await db.execute(select(Merchant))
    existing_merchants = {m.name for m in result.scalars().all()}

    for name, (patterns, cat_name) in SWISS_MERCHANTS.items():
        if name not in existing_merchants:
            db.add(Merchant(
                name=name,
                patterns=patterns,
                default_category_id=existing.get(cat_name),
                is_system=True,
            ))

    await db.commit()
