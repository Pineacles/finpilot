"""Transaction categorization engine.

Layered approach (priority order):
1. Keywords: direct Swiss-German keyword match
2. Merchant DB: fuzzy pattern match against known merchants
3. History: same merchant was categorized before
4. ML Classifier: scikit-learn model trained on user's own data
5. AI/LLM: fallback for unknowns (chunked, deduplicated)
6. Uncategorized: flagged for manual review
"""
import re
import json
import logging

logger = logging.getLogger(__name__)

import httpx
import anthropic
from thefuzz import fuzz
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Category, Transaction
from app.models.merchant import Merchant
from app.services.settings import get_setting
from app.services import classifier

# Swiss transaction normalization
PREFIXES = [
    (r"^TWINT\s+(Belastung|Gutschrift)\s*[-:]?\s*", "twint"),
    (r"^Zahlung\s*-\s*PAYPAL\s*\*", "paypal"),
    (r"^Zahlung\s*-\s*", "card"),
    (r"^E-Banking\s+Auftrag\s*", "e-banking"),
    (r"^Lastschrift\s*", "direct_debit"),
    (r"^Dauerauftrag\s*", "standing_order"),
    (r"^Belastung\s+eBill\s*", "ebill"),
    (r"^Einzahlung\s*-\s*", "deposit"),
    (r"^Tankomat\s*-\s*", "fuel"),
    (r"^Kartenzahlung\s*", "card"),
]


def normalize_description(raw: str) -> dict:
    """Clean Swiss bank transaction description into merchant name."""
    text = raw.strip()
    payment_method = None

    for pattern, method in PREFIXES:
        if re.match(pattern, text, re.IGNORECASE):
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            payment_method = method
            break

    # Strip reference numbers, dates, card numbers, phone numbers
    text = re.sub(r"\d{2}\.\d{2}\.\d{2,4}\s*\d{2}:\d{2}", "", text)  # datetime
    text = re.sub(r"\d{2}\.\d{2}\.\d{2,4}", "", text)  # date
    text = re.sub(r"Karten?-?Nr\.?\s*\d+\*+\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\+\d{10,}", "", text)  # phone numbers
    text = re.sub(r"\b\d{10,}\b", "", text)  # long reference numbers
    text = re.sub(r"\s*-\s*$", "", text)  # trailing dash
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "merchant": text,
        "payment_method": payment_method,
        "normalized": text.lower(),
    }


# Known Swiss transaction types that map directly to categories
DIRECT_CATEGORY_MAP = {
    "gehaltszahlung": "Salary",
    "lohnzahlung": "Salary",
    "miete": "Rent",
    "mietzins": "Rent",
    "bargeldbezug": "Cash",
    "bancomat": "Cash",
    "einzahlung": "Cash",
    "setgebühr": "Bank Fees",
    "setgebuhr": "Bank Fees",
    "kontoführung": "Bank Fees",
    "kontofuhrung": "Bank Fees",
    "viseca payment services": "Transfer",
    "viseca card services": "Transfer",
    "cembra": "Transfer",
    "cumulus": "Transfer",
    "migros bank cumulus": "Transfer",
    "steuern": "Taxes",
    "steueramt": "Taxes",
    "serafe": "Utilities",
    "billag": "Utilities",
}


def is_person_name(text: str) -> bool:
    """Check if the cleaned merchant looks like a person name (not a business)."""
    cleaned = re.sub(r"\+\d+", "", text).strip()
    cleaned = re.sub(r"\d{10,}", "", cleaned).strip()
    if not cleaned:
        return False
    words = cleaned.split()
    if len(words) > 3:
        return False
    if any(c in cleaned for c in [".", "&", "GmbH", "AG", "SA", "Sàrl", "@"]):
        return False
    return all(w[0].isupper() and w[1:].islower() if len(w) > 1 else True for w in words)


# ── Fuzzy merchant matching ─────────────────────────────────────────
FUZZY_THRESHOLD = 80  # Minimum fuzz ratio for a match


def _fuzzy_match_merchant(merchants: list[Merchant], search_text: str) -> Merchant | None:
    """Match against merchant DB using exact substring first, then fuzzy."""
    search_lower = search_text.lower()

    # Pass 1: exact substring (fast, existing behavior)
    for m in merchants:
        patterns = m.patterns.split("|") if m.patterns else []
        for p in patterns:
            if p and p.lower() in search_lower:
                return m

    # Pass 2: fuzzy match on merchant name and patterns
    best_match = None
    best_score = 0
    for m in merchants:
        # Check merchant name
        score = fuzz.partial_ratio(m.name.lower(), search_lower)
        if score > best_score:
            best_score = score
            best_match = m

        # Check each pattern
        patterns = m.patterns.split("|") if m.patterns else []
        for p in patterns:
            if not p:
                continue
            score = fuzz.partial_ratio(p.lower(), search_lower)
            if score > best_score:
                best_score = score
                best_match = m

    if best_score >= FUZZY_THRESHOLD and best_match:
        return best_match
    return None


# ── Main categorization function ─────────────────────────────────────

async def categorize_transaction(
    db: AsyncSession, user_id: str, description: str, amount: float,
    counterparty: str = "", payment_method: str = "",
) -> tuple[str | None, str, str, float]:
    """Categorize a transaction. Returns (category_id, merchant_name, method, confidence)."""
    parsed = normalize_description(description)
    merchant_name = counterparty or parsed["merchant"]
    normalized = parsed["normalized"]
    pm = payment_method or parsed["payment_method"] or ""

    # 0. Merchant DB lookup FIRST: user-created rules take priority over keywords
    result = await db.execute(select(Merchant).where(Merchant.user_id == user_id))
    merchants = result.scalars().all()
    search_text = f"{normalized} {counterparty.lower()}"
    matched = _fuzzy_match_merchant(merchants, search_text)
    if matched:
        return matched.default_category_id, matched.name, "merchant_db", 0.95

    # 1a. TWINT with person name = Transfer (friends)
    if pm == "twint" and is_person_name(parsed["merchant"]):
        cat = await _find_category(db, user_id, "Transfer")
        if cat:
            return cat.id, merchant_name, "keyword", 0.95

    # 1b. Any incoming money (positive amount) = Income by default
    if amount > 0:
        cat_name = "Salary" if "gehalt" in normalized or "lohn" in normalized else "Income"
        cat = await _find_category(db, user_id, cat_name)
        if cat:
            return cat.id, merchant_name, "keyword", 0.9

    # 1c. "Vergütung" = e-banking payment
    if "vergütung" in normalized or "vergutung" in normalized:
        if counterparty:
            merchant_name = counterparty
            # Fall through to history/classifier
        else:
            cat = await _find_category(db, user_id, "Other")
            if cat:
                return cat.id, "E-Banking Payment", "keyword", 0.5

    # 1d. Direct keyword match for Swiss transaction types
    for keyword, cat_name in DIRECT_CATEGORY_MAP.items():
        if keyword in normalized:
            cat = await _find_category(db, user_id, cat_name)
            if cat:
                return cat.id, merchant_name, "keyword", 1.0

    # 2. History: same merchant was categorized before
    result = await db.execute(
        select(Transaction.category_id, func.count().label("cnt"))
        .where(and_(
            Transaction.user_id == user_id,
            Transaction.merchant == merchant_name,
            Transaction.category_id.isnot(None),
        ))
        .group_by(Transaction.category_id)
        .order_by(func.count().desc())
        .limit(1)
    )
    history = result.first()
    if history and history.cnt >= 1:
        return history.category_id, merchant_name, "history", 0.85

    # 3. ML classifier (trained on user's own data)
    cat_id, cat_name, confidence = classifier.predict(
        user_id, merchant_name, description, amount
    )
    if cat_id and confidence >= 0.6:
        return cat_id, merchant_name, "classifier", confidence

    # 4. Return uncategorized: AI will be run in batch
    return None, merchant_name, "unmatched", 0.0


# ── AI batch categorization ──────────────────────────────────────────

CHUNK_SIZE = 20  # Max merchants per AI call


async def _build_category_tree_prompt(db: AsyncSession, user_id: str) -> tuple[str, dict[str, str]]:
    """Build category list for AI prompt showing parent > sub hierarchy.

    Returns (prompt_text, name_to_id_map).
    """
    result = await db.execute(
        select(Category).where(Category.user_id == user_id)
    )
    all_cats = result.scalars().all()
    cat_map = {c.name: c.id for c in all_cats}

    # Build tree structure
    parents = [c for c in all_cats if c.parent_id is None]
    children = {}
    for c in all_cats:
        if c.parent_id:
            children.setdefault(c.parent_id, []).append(c)

    lines = []
    for p in sorted(parents, key=lambda x: x.name):
        kids = children.get(p.id, [])
        if kids:
            kid_names = ", ".join(sorted(k.name for k in kids))
            lines.append(f"{p.name} ({kid_names})")
        else:
            lines.append(p.name)

    return "\n".join(lines), cat_map


async def batch_categorize_with_ai(
    db: AsyncSession, user_id: str, transactions: list[dict]
) -> list[dict]:
    """Batch categorize using AI. Sends in chunks of CHUNK_SIZE.

    transactions: [{"id": ..., "description": ..., "amount": ..., "merchant": ...}]
    Returns: [{"id": ..., "category_id": ..., "category_name": ..., "confidence": ...}]
    """
    if not transactions:
        return []

    cat_tree_prompt, categories = await _build_category_tree_prompt(db, user_id)

    # Load AI settings once
    custom_endpoint = await get_setting(db, user_id, "ai_endpoint")
    auth_header = await get_setting(db, user_id, "ai_auth_header")
    api_key = await get_setting(db, user_id, "anthropic_api_key")
    model = await get_setting(db, user_id, "ai_model") or "claude-haiku-4-5-20251001"

    if not custom_endpoint and not api_key:
        logger.warning("No AI backend configured for categorization")
        return []

    all_results: list[dict] = []
    for chunk_start in range(0, len(transactions), CHUNK_SIZE):
        chunk = transactions[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_num = chunk_start // CHUNK_SIZE + 1
        total_chunks = (len(transactions) + CHUNK_SIZE - 1) // CHUNK_SIZE
        logger.info(f"AI categorize chunk {chunk_num}/{total_chunks} ({len(chunk)} merchants)")

        txn_lines = "\n".join(
            f'{i+1}. {t["merchant"]} | CHF {t["amount"]}'
            for i, t in enumerate(chunk)
        )

        prompt = f"""Categorize these Swiss bank transactions. Use the MOST SPECIFIC subcategory.

Category hierarchy (Parent > Subcategories):
{cat_tree_prompt}

Transactions:
{txn_lines}

Return ONLY a JSON array, one object per transaction in order:
[{{"m":"merchant","c":"SUBCATEGORY name","s":0.9}}]

Rules:
- c MUST exactly match a category name from above (prefer subcategory over parent)
- s = confidence 0.0-1.0
- Person names (first+last name only) = Transfer
- Food delivery apps = Delivery
- Restaurants / cafes = Restaurants or Cafe & Snacks
- Digital subscriptions (Netflix, Spotify, OpenAI, YouTube, gaming subs) = Subscriptions
- Video games / gaming platforms = Gaming
- Supermarkets = Supermarket, convenience stores = Convenience
- Online stores (Amazon, BRACK, Galaxus) = Online Shopping
- Government offices / Strassenverkehrsamt / fines = Government Fees
- Bank fees / Setgebuehr / card fees = Bank Fees
- Health insurance (Concordia, CSS, Helsana) = Insurance
- University / school = Tuition
- Fuel stations (Shell, BP, Migrol, Tankomat) = Fuel
- Parking (Parkingpay) = Parking
- Car maintenance / garage = Maintenance
- Train / bus = Public Transport
JSON only, no explanation."""

        chunk_results = await _call_ai(
            custom_endpoint, auth_header, api_key, model, prompt, chunk,
        )

        for i, txn in enumerate(chunk):
            if i < len(chunk_results):
                r = chunk_results[i]
                cat_name = r.get("c") or r.get("category", "Other")
                cat_id = categories.get(cat_name)
                confidence = r.get("s") or r.get("confidence", 0.5)
                all_results.append({
                    "id": txn["id"], "category_id": cat_id,
                    "category_name": cat_name, "confidence": float(confidence),
                })
            else:
                all_results.append({
                    "id": txn["id"], "category_id": None,
                    "category_name": "Other", "confidence": 0.0,
                })

    return all_results


async def _call_ai(
    custom_endpoint: str | None, auth_header: str | None,
    api_key: str | None, model: str,
    prompt: str, transactions: list[dict],
) -> list[dict]:
    """Call AI backend and parse response."""
    try:
        if custom_endpoint:
            headers = {"Content-Type": "application/json"}
            if auth_header:
                headers["Authorization"] = auth_header
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(custom_endpoint, headers=headers, json={
                    "analysis_type": "categorize",
                    "model": "claude-haiku-4-5-20251001",
                    "system_prompt": "You are a Swiss personal finance assistant. Return ONLY valid JSON.",
                    "user_prompt": prompt,
                    "transactions": transactions,
                })
                resp.raise_for_status()
                result_data = resp.json()
                logger.info(f"AI response keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'array'}")
                return _parse_ai_response(result_data)
        elif api_key:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return _parse_json_text(text)
        return []
    except Exception as e:
        logger.error(f"AI categorization chunk failed: {e}", exc_info=True)
        return []


def _parse_ai_response(result_data: dict | list) -> list[dict]:
    """Parse various AI response formats into a list of dicts."""
    if isinstance(result_data, list):
        return result_data

    for key in ("content", "text", "results"):
        if key not in result_data:
            continue
        val = result_data[key]
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return _parse_json_text(val)
        if isinstance(val, dict):
            return [val]

    logger.warning(f"Could not parse AI response: {str(result_data)[:200]}")
    return []


def _parse_json_text(text: str) -> list[dict]:
    """Parse JSON from text that may be wrapped in markdown code blocks."""
    text = text.strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else [result]
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI JSON: {e}, text: {text[:200]}")
        return []


async def _ai_categorize_with_custom_prompt(
    db: AsyncSession, user_id: str, transactions: list[dict], custom_prompt: str
) -> list[dict]:
    """Categorize with a user-provided custom prompt. Uses chunking."""
    if not transactions:
        return []

    cat_tree_prompt, categories = await _build_category_tree_prompt(db, user_id)

    custom_endpoint = await get_setting(db, user_id, "ai_endpoint")
    auth_header = await get_setting(db, user_id, "ai_auth_header")
    api_key = await get_setting(db, user_id, "anthropic_api_key")
    model = await get_setting(db, user_id, "ai_model") or "claude-haiku-4-5-20251001"

    all_results: list[dict] = []
    for chunk_start in range(0, len(transactions), CHUNK_SIZE):
        chunk = transactions[chunk_start:chunk_start + CHUNK_SIZE]
        txn_lines = "\n".join(
            f'{i+1}. {t["merchant"]} | CHF {t["amount"]}'
            for i, t in enumerate(chunk)
        )

        prompt = f"""User rules: {custom_prompt}

Category hierarchy:
{cat_tree_prompt}

Transactions:
{txn_lines}

Return ONLY JSON array: [{{"m":"merchant","c":"subcategory","s":0.9}}]
c must exactly match a category name. Use most specific subcategory. Follow user rules. JSON only."""

        chunk_results = await _call_ai(custom_endpoint, auth_header, api_key, model, prompt, chunk)

        for i, txn in enumerate(chunk):
            if i < len(chunk_results):
                r = chunk_results[i]
                cat_name = r.get("c") or r.get("category", "Other")
                cat_id = categories.get(cat_name)
                confidence = r.get("s") or r.get("confidence", 0.5)
                all_results.append({"id": txn["id"], "category_id": cat_id, "category_name": cat_name, "confidence": float(confidence)})
            else:
                all_results.append({"id": txn["id"], "category_id": None, "category_name": "Other", "confidence": 0.0})

    return all_results


async def _find_category(db: AsyncSession, user_id: str, name: str) -> Category | None:
    result = await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == name))
    )
    return result.scalar_one_or_none()
