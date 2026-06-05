"""Seed category hierarchy and Swiss merchant database."""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.models.finance import Category

logger = logging.getLogger(__name__)

# ── Category hierarchy ──────────────────────────────────────────────
# { "Parent": ["Sub1", "Sub2", ...] }
# Categories without subs are standalone (no children).
CATEGORY_TREE: dict[str, dict] = {
    "Housing": {
        "type": "expense",
        "subs": ["Rent", "Utilities", "Household"],
    },
    "Groceries": {
        "type": "expense",
        "subs": ["Supermarket", "Convenience"],
    },
    "Dining": {
        "type": "expense",
        "subs": ["Restaurants", "Delivery", "Cafe & Snacks"],
    },
    "Transport": {
        "type": "expense",
        "subs": ["Public Transport", "Taxi & Rides"],
    },
    "Car": {
        "type": "expense",
        "subs": ["Fuel", "Parking", "Maintenance", "Car Insurance"],
    },
    "Entertainment": {
        "type": "expense",
        "subs": ["Subscriptions", "Gaming", "Going Out"],
    },
    "Shopping": {
        "type": "expense",
        "subs": ["Online Shopping", "Clothing", "Electronics"],
    },
    "Health": {
        "type": "expense",
        "subs": ["Insurance", "Medical", "Fitness", "Personal Care"],
    },
    "Education": {
        "type": "expense",
        "subs": ["Tuition", "Learning"],
    },
    "Telecom": {
        "type": "expense",
        "subs": ["Mobile", "Internet"],
    },
    "Finance": {
        "type": "expense",
        "subs": ["Bank Fees", "Investments"],
    },
    "Taxes & Fees": {
        "type": "expense",
        "subs": ["Taxes", "Government Fees"],
    },
    "Travel": {
        "type": "expense",
        "subs": ["Flights", "Accommodation", "Activities"],
    },
    "Gifts & Donations": {
        "type": "expense",
        "subs": [],
    },
    "Income": {
        "type": "income",
        "subs": ["Salary", "Side Income", "Refunds"],
    },
    "Cash": {
        "type": "expense",
        "subs": [],
    },
    "Transfer": {
        "type": "transfer",
        "subs": [],
    },
    "Other": {
        "type": "expense",
        "subs": [],
    },
}

# ── Merchant patterns → subcategory ────────────────────────────────
# merchant_name: (patterns pipe-separated, subcategory_name)
# Transactions are categorized to the MOST SPECIFIC (sub) category.
SWISS_MERCHANTS = {
    # Groceries > Supermarket
    "Migros": ("migros", "Supermarket"),
    "Coop": ("coop-|coop ", "Supermarket"),
    "Denner": ("denner", "Supermarket"),
    "Aldi": ("aldi", "Supermarket"),
    "Lidl": ("lidl", "Supermarket"),
    "Volg": ("volg", "Supermarket"),
    "Spar": ("spar ", "Supermarket"),
    "Landi": ("landi ", "Supermarket"),
    # Groceries > Convenience
    "Kiosk": ("kiosk|avec", "Convenience"),
    # Dining > Restaurants
    "McDonald's": ("mcdonald", "Restaurants"),
    "Burger King": ("burger king", "Restaurants"),
    "Starbucks": ("starbucks", "Cafe & Snacks"),
    # Dining > Delivery
    "JustEat": ("justeat|just eat|eat.ch", "Delivery"),
    "Uber Eats": ("uber eats", "Delivery"),
    # Transport > Public Transport
    "SBB": ("sbb|schweizerische bundesbahnen", "Public Transport"),
    "BLS": ("bls ", "Public Transport"),
    "ZVV": ("zvv", "Public Transport"),
    # Car > Fuel
    "AGROLA": ("agrola", "Fuel"),
    "Migrol": ("migrol", "Fuel"),
    "Shell": ("shell |shell-", "Fuel"),
    "BP": ("bp tankstelle|bp ", "Fuel"),
    # Car > Parking
    "Parkingpay": ("parkingpay", "Parking"),
    # Entertainment > Subscriptions
    "Netflix": ("netflix", "Subscriptions"),
    "Spotify": ("spotify", "Subscriptions"),
    "YouTube": ("youtube|google youtube", "Subscriptions"),
    "Disney+": ("disney", "Subscriptions"),
    "Apple": ("apple.com|apple store", "Subscriptions"),
    "Google One": ("google one", "Subscriptions"),
    # Entertainment > Gaming
    "Steam": ("steam", "Gaming"),
    # Shopping > Online Shopping
    "Galaxus": ("galaxus|digitec", "Online Shopping"),
    "Zalando": ("zalando", "Clothing"),
    "Amazon": ("amazon|amzn", "Online Shopping"),
    "BRACK.CH": ("brack.ch|brack ", "Online Shopping"),
    "Manor": ("manor", "Online Shopping"),
    # Shopping
    "IKEA": ("ikea", "Household"),
    # Telecom
    "Swisscom": ("swisscom", "Mobile"),
    "Sunrise": ("sunrise", "Mobile"),
    "Salt": ("salt mobile", "Mobile"),
    # Health > Insurance
    "CSS": ("css versicherung|css kranken", "Insurance"),
    "Helsana": ("helsana", "Insurance"),
    "Visana": ("visana", "Insurance"),
    "Concordia": ("concordia", "Insurance"),
    "Mobiliar": ("mobiliar", "Insurance"),
    "AXA": ("axa ", "Insurance"),
    # Finance
    "Viseca": ("viseca payment|viseca card", "Transfer"),
    "PostFinance": ("postfinance", "Transfer"),
    "PayPal": ("paypal", "Online Shopping"),
    "Revolut": ("revolut", "Transfer"),
    # Taxes & Fees
    "Strassenverkehrsamt": ("strassenverkehrsamt", "Government Fees"),
}


async def seed_merchants(db: AsyncSession, user_id: str):
    """Seed category hierarchy and merchant database."""
    # 1. Build full category tree
    result = await db.execute(select(Category).where(Category.user_id == user_id))
    existing = {c.name: c for c in result.scalars().all()}

    cat_id_map: dict[str, str] = {}  # name -> id

    for parent_name, info in CATEGORY_TREE.items():
        cat_type = info["type"]
        subs = info["subs"]

        # Create parent if missing
        if parent_name in existing:
            parent = existing[parent_name]
            cat_id_map[parent_name] = parent.id
        else:
            parent = Category(user_id=user_id, name=parent_name, type=cat_type)
            db.add(parent)
            await db.flush()
            cat_id_map[parent_name] = parent.id
            existing[parent_name] = parent

        # Create subcategories
        for sub_name in subs:
            if sub_name in existing:
                # Ensure parent_id is set (might be old flat category)
                sub = existing[sub_name]
                if sub.parent_id != parent.id:
                    sub.parent_id = parent.id
                cat_id_map[sub_name] = sub.id
            else:
                sub = Category(
                    user_id=user_id, name=sub_name, type=cat_type,
                    parent_id=parent.id,
                )
                db.add(sub)
                await db.flush()
                cat_id_map[sub_name] = sub.id
                existing[sub_name] = sub

    # 2. Seed merchants
    result = await db.execute(select(Merchant).where(Merchant.user_id == user_id))
    existing_merchants = {m.name: m for m in result.scalars().all()}

    for name, (patterns, cat_name) in SWISS_MERCHANTS.items():
        cat_id = cat_id_map.get(cat_name)
        if name in existing_merchants:
            # Update existing merchant if category changed
            m = existing_merchants[name]
            if cat_id and m.default_category_id != cat_id:
                m.default_category_id = cat_id
                m.patterns = patterns
        else:
            db.add(Merchant(
                user_id=user_id,
                name=name,
                patterns=patterns,
                default_category_id=cat_id,
                is_system=True,
            ))

    await db.commit()
    logger.info(f"Seeded {len(cat_id_map)} categories and {len(SWISS_MERCHANTS)} merchants for user {user_id}")
