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
from dataclasses import dataclass

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
DEFAULT_AI_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class AiConfig:
    """Resolved, per-user AI backend configuration for one categorization run."""
    enabled: bool
    provider: str  # "anthropic" | "openai" | "custom"
    api_key: str
    model: str
    endpoint: str  # custom provider only
    auth_header: str  # custom provider only
    base_url: str  # openai provider only


async def load_ai_config(db: AsyncSession, user_id: str) -> AiConfig:
    """Load the user's AI settings once and resolve them into an AiConfig.

    Provider inference when ai_provider is unset: "custom" if ai_endpoint is
    set, else "anthropic". A provider is usable only when the setting it
    needs is present (custom: endpoint, anthropic: api key, openai: base
    url); ai_enabled="0" disables regardless of usability.
    """
    ai_enabled = await get_setting(db, user_id, "ai_enabled")
    provider = await get_setting(db, user_id, "ai_provider")
    api_key = await get_setting(db, user_id, "ai_api_key")
    model = await get_setting(db, user_id, "ai_model") or DEFAULT_AI_MODEL
    endpoint = await get_setting(db, user_id, "ai_endpoint")
    auth_header = await get_setting(db, user_id, "ai_auth_header")
    base_url = await get_setting(db, user_id, "ai_base_url")

    if not provider:
        provider = "custom" if endpoint else "anthropic"

    if provider == "custom":
        usable = bool(endpoint)
    elif provider == "openai":
        usable = bool(base_url)
    else:  # anthropic
        usable = bool(api_key)

    enabled = ai_enabled != "0" and usable

    return AiConfig(
        enabled=enabled, provider=provider, api_key=api_key, model=model,
        endpoint=endpoint, auth_header=auth_header, base_url=base_url,
    )


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


def _build_prompt(cat_tree_prompt: str, chunk: list[dict], custom_rules: str | None = None) -> str:
    """Build the categorization prompt for one chunk of transactions.

    Shared by batch_categorize_with_ai and the settings "test AI" endpoint
    so both send the model the exact same instructions. custom_rules is an
    optional per-request instruction block (the transactions page lets the
    user steer a one-off AI categorization run); it takes priority over the
    built-in rules.
    """
    txn_lines = "\n".join(
        f'{i+1}. {t["merchant"]} | CHF {t["amount"]}'
        for i, t in enumerate(chunk)
    )

    custom_block = (
        f"\nUser rules (follow these with priority over the rules below):\n{custom_rules}\n"
        if custom_rules else ""
    )

    return f"""Categorize these Swiss bank transactions. Use the MOST SPECIFIC subcategory.
{custom_block}

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


def _parse_ai_results(chunk_results: list[dict], chunk: list[dict], categories: dict[str, str]) -> list[dict]:
    """Map raw AI result dicts onto the chunk's transaction ids."""
    results = []
    for i, txn in enumerate(chunk):
        if i < len(chunk_results):
            r = chunk_results[i]
            cat_name = r.get("c") or r.get("category", "Other")
            cat_id = categories.get(cat_name)
            # Explicit None checks: `or` would turn a legitimate confidence
            # of 0.0 into the 0.5 fallback.
            confidence = r.get("s")
            if confidence is None:
                confidence = r.get("confidence")
            if confidence is None:
                confidence = 0.5
            results.append({
                "id": txn["id"], "category_id": cat_id,
                "category_name": cat_name, "confidence": float(confidence),
            })
        else:
            results.append({
                "id": txn["id"], "category_id": None,
                "category_name": "Other", "confidence": 0.0,
            })
    return results


async def batch_categorize_with_ai(
    db: AsyncSession, user_id: str, transactions: list[dict],
    custom_rules: str | None = None,
) -> tuple[list[dict], list[str]]:
    """Batch categorize using AI. Sends in chunks of CHUNK_SIZE.

    transactions: [{"id": ..., "description": ..., "amount": ..., "merchant": ...}]
    custom_rules: optional per-request user instructions, see _build_prompt.
    Returns: (results, errors).
    results: [{"id": ..., "category_id": ..., "category_name": ..., "confidence": ...}]
    errors: one human-readable message per chunk that failed to call the AI backend.
    """
    if not transactions:
        return [], []

    config = await load_ai_config(db, user_id)
    if not config.enabled:
        logger.warning("AI categorization disabled or not configured for user %s", user_id[:8])
        return [], ["AI categorization disabled or not configured"]

    cat_tree_prompt, categories = await _build_category_tree_prompt(db, user_id)

    all_results: list[dict] = []
    errors: list[str] = []
    for chunk_start in range(0, len(transactions), CHUNK_SIZE):
        chunk = transactions[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_num = chunk_start // CHUNK_SIZE + 1
        total_chunks = (len(transactions) + CHUNK_SIZE - 1) // CHUNK_SIZE
        logger.info(f"AI categorize chunk {chunk_num}/{total_chunks} ({len(chunk)} merchants)")

        prompt = _build_prompt(cat_tree_prompt, chunk, custom_rules)
        chunk_results, error = await _call_ai(config, prompt, chunk)
        if error:
            errors.append(error)

        all_results.extend(_parse_ai_results(chunk_results, chunk, categories))

    return all_results, errors


async def _call_ai(
    config: AiConfig, prompt: str, transactions: list[dict],
) -> tuple[list[dict], str | None]:
    """Call the configured AI provider and parse its response.

    Returns (results, error). On failure results is [] and error is a short
    human-readable message identifying the provider and the cause.
    """
    try:
        if config.provider == "anthropic":
            client = anthropic.AsyncAnthropic(api_key=config.api_key)
            response = await client.messages.create(
                model=config.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return _parse_json_text(text), None

        if config.provider == "openai":
            headers = {}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _parse_json_text(content), None

        # custom
        headers = {"Content-Type": "application/json"}
        if config.auth_header:
            headers["Authorization"] = config.auth_header
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(config.endpoint, headers=headers, json={
                "analysis_type": "categorize",
                "model": config.model,
                "system_prompt": "You are a Swiss personal finance assistant. Return ONLY valid JSON.",
                "user_prompt": prompt,
                "transactions": transactions,
            })
            resp.raise_for_status()
            result_data = resp.json()
            return _parse_ai_response(result_data), None
    except httpx.HTTPStatusError as e:
        logger.error(f"AI categorization chunk failed: {e}", exc_info=True)
        return [], f"{config.provider} endpoint returned {e.response.status_code} {e.response.reason_phrase}"
    except Exception as e:
        logger.error(f"AI categorization chunk failed: {e}", exc_info=True)
        return [], f"{config.provider} call failed: {e}"


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


async def _find_category(db: AsyncSession, user_id: str, name: str) -> Category | None:
    result = await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == name))
    )
    return result.scalar_one_or_none()
