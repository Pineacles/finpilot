"""Transaction categorization engine.

Layered approach (priority order):
1. Merchant DB — exact pattern match against known merchants
2. History — same normalized description was categorized before
3. AI/LLM — fallback for unknowns (uses settings endpoint or Anthropic)
4. Uncategorized — flagged for manual review
"""
import re
import json
import logging

logger = logging.getLogger(__name__)

import httpx
import anthropic
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Category, Transaction
from app.models.merchant import Merchant, CategorizationLog
from app.services.settings import get_setting

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
    text = re.sub(r"Karten?-?Nr\.?\s*\d+\*+\d+", "", text, flags=re.IGNORECASE)  # card number
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
}

# TWINT with a person name (no business identifier) = transfer to/from friends
# Pattern: just a first name + optional last name + phone number
TWINT_PERSON_PATTERN = re.compile(
    r"^[\s]*[A-ZÄÖÜ][a-zäöüéèê]+(?:\s+[A-ZÄÖÜ][a-zäöüéèê]+)?$"
)


def is_person_name(text: str) -> bool:
    """Check if the cleaned merchant looks like a person name (not a business)."""
    cleaned = re.sub(r"\+\d+", "", text).strip()
    cleaned = re.sub(r"\d{10,}", "", cleaned).strip()
    # Person names: 1-2 words, each capitalized, no special business chars
    if not cleaned:
        return False
    words = cleaned.split()
    if len(words) > 3:
        return False
    if any(c in cleaned for c in [".", "&", "GmbH", "AG", "SA", "Sàrl", "@"]):
        return False
    return all(w[0].isupper() and w[1:].islower() if len(w) > 1 else True for w in words)


async def categorize_transaction(
    db: AsyncSession, user_id: str, description: str, amount: float,
    counterparty: str = "", payment_method: str = "",
) -> tuple[str | None, str, str, float]:
    """Categorize a transaction. Returns (category_id, merchant_name, method, confidence)."""
    parsed = normalize_description(description)
    merchant_name = counterparty or parsed["merchant"]
    normalized = parsed["normalized"]
    pm = payment_method or parsed["payment_method"] or ""

    # 0a. TWINT with person name = Transfer (friends)
    if pm == "twint" and is_person_name(parsed["merchant"]):
        cat_name = "Transfer"
        cat = await _find_category(db, user_id, cat_name)
        if cat:
            return cat.id, merchant_name, "keyword", 0.95

    # 0b. Any incoming money (positive amount) = Income by default
    if amount > 0:
        # Salary has its own keyword match below, this catches the rest
        cat_name = "Salary" if "gehalt" in normalized or "lohn" in normalized else "Income"
        cat = await _find_category(db, user_id, cat_name)
        if cat:
            return cat.id, merchant_name, "keyword", 0.9

    # 0c. "Vergütung" in CSV = e-banking payment (the CSV lacks detail, camt.053 is better)
    # If we have a counterparty from camt.053, use that. Otherwise mark as "Bills"
    if "vergütung" in normalized or "vergutung" in normalized:
        if counterparty:
            merchant_name = counterparty
            # Fall through to merchant DB lookup with counterparty name
        else:
            cat = await _find_category(db, user_id, "Other")
            if cat:
                return cat.id, "E-Banking Payment", "keyword", 0.5

    # 0d. Direct keyword match for Swiss transaction types
    for keyword, cat_name in DIRECT_CATEGORY_MAP.items():
        if keyword in normalized:
            cat = await _find_category(db, user_id, cat_name)
            if cat:
                return cat.id, merchant_name, "keyword", 1.0

    # 1. Merchant DB lookup (also checks counterparty name)
    result = await db.execute(select(Merchant))
    merchants = result.scalars().all()
    search_text = f"{normalized} {counterparty.lower()}"
    for m in merchants:
        patterns = m.patterns.split("|") if m.patterns else []
        for p in patterns:
            if p and p.lower() in search_text:
                return m.default_category_id, m.name, "merchant_db", 0.95

    # 2. History — same normalized description was categorized before
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

    # 3. Return uncategorized — AI will be run in batch
    return None, merchant_name, "unmatched", 0.0


CHUNK_SIZE = 20  # Max merchants per AI call — keeps prompts small and responses reliable


async def batch_categorize_with_ai(
    db: AsyncSession, user_id: str, transactions: list[dict]
) -> list[dict]:
    """Batch categorize uncategorized transactions using AI.

    Sends in chunks of CHUNK_SIZE for reliable responses.
    transactions: [{"id": ..., "description": ..., "amount": ..., "merchant": ...}]
    Returns: [{"id": ..., "category_id": ..., "category_name": ..., "confidence": ...}]
    """
    if not transactions:
        return []

    # Get user's categories
    result = await db.execute(
        select(Category).where(Category.user_id == user_id)
    )
    categories = {c.name: c.id for c in result.scalars().all()}
    cat_list = list(categories.keys())

    # Load AI settings once
    custom_endpoint = await get_setting(db, user_id, "analysis_endpoint")
    auth_header = await get_setting(db, user_id, "analysis_auth_header")
    api_key = await get_setting(db, user_id, "anthropic_api_key")
    model = await get_setting(db, user_id, "analysis_model") or "claude-haiku-4-5-20251001"

    if not custom_endpoint and not api_key:
        logger.warning("No AI backend configured for categorization")
        return []

    # Process in chunks
    all_results: list[dict] = []
    for chunk_start in range(0, len(transactions), CHUNK_SIZE):
        chunk = transactions[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_num = chunk_start // CHUNK_SIZE + 1
        total_chunks = (len(transactions) + CHUNK_SIZE - 1) // CHUNK_SIZE
        logger.info(f"AI categorize chunk {chunk_num}/{total_chunks} ({len(chunk)} merchants)")

        txn_lines = "\n".join(f'{i+1}. {t["merchant"]} | CHF {t["amount"]}' for i, t in enumerate(chunk))

        prompt = f"""Categorize these Swiss bank transactions into exactly one category each.

Categories: {", ".join(cat_list)}

Transactions:
{txn_lines}

Return ONLY a JSON array, one object per transaction in same order:
[{{"m":"merchant name","c":"category","s":0.9}}]

Rules:
- c MUST be from the categories list above
- s = confidence 0.0-1.0
- Person names (first+last) = Transfer
- Food delivery / restaurants = Dining
- Subscriptions (Netflix, Spotify, OpenAI, Google services) = Entertainment
- Gaming (Riot, Steam, etc) = Entertainment
- Online shopping = Shopping
- Government / Strassenverkehrsamt / fees = Taxes
- Bank fees / Setgebühr = Other
- Education (Hochschule, courses) = Education
- Health insurance (Concordia, CSS, etc) = Insurance
JSON only, no explanation."""

        chunk_results = await _call_ai(
            custom_endpoint, auth_header, api_key, model,
            prompt, chunk,
        )

        # Map results back
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
    """Call AI backend and parse response. Returns list of result dicts."""
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

    # Try each known response key
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
    # Strip markdown code blocks
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    # Find JSON array in text (sometimes AI adds explanation before/after)
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
    """Categorize with a user-provided custom prompt injected. Uses chunking."""
    if not transactions:
        return []

    result = await db.execute(select(Category).where(Category.user_id == user_id))
    categories = {c.name: c.id for c in result.scalars().all()}
    cat_list = list(categories.keys())

    custom_endpoint = await get_setting(db, user_id, "analysis_endpoint")
    auth_header = await get_setting(db, user_id, "analysis_auth_header")
    api_key = await get_setting(db, user_id, "anthropic_api_key")
    model = await get_setting(db, user_id, "analysis_model") or "claude-haiku-4-5-20251001"

    all_results: list[dict] = []
    for chunk_start in range(0, len(transactions), CHUNK_SIZE):
        chunk = transactions[chunk_start:chunk_start + CHUNK_SIZE]
        txn_lines = "\n".join(f'{i+1}. {t["merchant"]} | CHF {t["amount"]}' for i, t in enumerate(chunk))

        prompt = f"""User rules: {custom_prompt}

Categories: {", ".join(cat_list)}

Transactions:
{txn_lines}

Return ONLY JSON array: [{{"m":"merchant","c":"category","s":0.9}}]
c must be from categories. Follow user rules above. JSON only."""

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
