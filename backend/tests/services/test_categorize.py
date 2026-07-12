"""Transaction categorization engine: keyword map, merchant-DB fuzzy
match, income default, history fallback, and the AI batch path's
hermetic early-return when no AI backend is configured.

Follows test_settlement.py / test_mapped_import.py conventions: real ORM
rows via Account/Transaction/Category, seed_merchants(db, user_id) for
the category tree + merchant DB, and no network calls anywhere.
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
from sqlalchemy import select, and_

# Captured before any test monkeypatches categorize.httpx.AsyncClient (which
# is the same module-level attribute this test file's `httpx` import sees):
# the mock-transport factories below need the *real* class, not themselves.
_RealAsyncClient = httpx.AsyncClient

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.services import categorize
from app.services.categorize import batch_categorize_with_ai, categorize_transaction
from app.services.seed_merchants import seed_merchants


async def _category(db, user_id, name: str) -> Category:
    result = await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == name))
    )
    return result.scalar_one()


async def test_direct_keyword_match_resolves_rent(db, user_id):
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Miete Wohnung Oktober", -1800.0,
    )

    rent = await _category(db, user_id, "Rent")
    assert method == "keyword"
    assert cat_id == rent.id
    assert confidence == pytest.approx(1.0)


async def test_merchant_db_fuzzy_match_resolves_migros(db, user_id):
    await seed_merchants(db, user_id)

    # Misspelled merchant name (typo: "Migeos"), must not match any
    # DIRECT_CATEGORY_MAP keyword, only the fuzzy merchant-DB pass.
    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Migeos Zuerich Hauptbahnhof", -15.30,
    )

    supermarket = await _category(db, user_id, "Supermarket")
    assert method == "merchant_db"
    assert cat_id == supermarket.id
    assert merchant_name == "Migros"  # canonical seeded merchant name, not the raw text


async def test_positive_amount_defaults_to_income(db, user_id):
    """An ordinary positive amount from a business (not a person, not a
    salary/deposit keyword) still defaults to Income. Four words defeats
    the is_person_name() heuristic (it only accepts up to 3)."""
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Quarterly Freelance Invoice Payment", 500.0,
    )

    income = await _category(db, user_id, "Income")
    assert method == "keyword"
    assert cat_id == income.id
    assert merchant_name == "Quarterly Freelance Invoice Payment"


async def test_positive_amount_with_gehalt_resolves_salary(db, user_id):
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Gehaltszahlung März 2026", 6500.0,
    )

    salary = await _category(db, user_id, "Salary")
    assert method == "keyword"
    assert cat_id == salary.id


async def test_positive_amount_to_person_name_resolves_transfer(db, user_id):
    """A positive amount from a counterparty that looks like a person (e.g.
    a TWINT reimbursement from a friend that wasn't sent via TWINT itself)
    must land in Transfer, not Income."""
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Zahlung - Anna Suter", 50.0,
    )

    transfer = await _category(db, user_id, "Transfer")
    assert method == "keyword"
    assert cat_id == transfer.id
    assert merchant_name == "Anna Suter"


async def test_positive_einzahlung_resolves_transfer(db, user_id):
    """Own cash deposit ("Einzahlung ...") is money moving into the account
    from the same person, not real income."""
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Einzahlung Postomat 4111", 200.0,
    )

    transfer = await _category(db, user_id, "Transfer")
    assert method == "keyword"
    assert cat_id == transfer.id


async def test_history_fallback_reuses_prior_categorization(db, user_id):
    await seed_merchants(db, user_id)
    bank = Account(user_id=user_id, name="Valiant Bank", type="bank", currency="CHF")
    db.add(bank)
    await db.flush()

    side_income = await _category(db, user_id, "Side Income")
    prior = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 2, 1),
        merchant="Acme Freelance Client", amount=750.0, currency="CHF",
        category_id=side_income.id,
    )
    db.add(prior)
    await db.flush()
    await db.commit()

    # Negative amount and a description that doesn't hit the keyword map or
    # merchant DB: only the exact merchant-name history match should fire.
    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Payment Acme Freelance Client Invoice 2026-04", -200.0,
        counterparty="Acme Freelance Client",
    )

    assert method == "history"
    assert cat_id == side_income.id
    assert merchant_name == "Acme Freelance Client"


async def test_batch_categorize_with_ai_short_circuits_without_backend(db, user_id, monkeypatch):
    """No ai_endpoint / ai_api_key configured -> early return before any
    network call. Proves the function never reaches _call_ai when no AI
    backend is configured, regardless of the real environment's settings."""

    async def _no_setting(db_arg, user_id_arg, key):
        return None

    async def _must_not_be_called(*args, **kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr(categorize, "get_setting", _no_setting)
    monkeypatch.setattr(categorize, "_call_ai", _must_not_be_called)

    results, errors = await batch_categorize_with_ai(
        db, user_id,
        [{"id": "x", "merchant": "Some Unknown Shop", "description": "Some Unknown Shop", "amount": -10.0}],
    )

    assert results == []
    assert errors == ["AI categorization disabled or not configured"]


async def test_batch_categorize_with_ai_short_circuits_when_disabled(db, user_id, monkeypatch):
    """ai_enabled="0" disables the AI fallback even if a provider is otherwise
    fully configured, and never reaches _call_ai."""

    async def _fake_setting(db_arg, user_id_arg, key):
        return {"ai_enabled": "0", "ai_api_key": "sk-test"}.get(key, "")

    async def _must_not_be_called(*args, **kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr(categorize, "get_setting", _fake_setting)
    monkeypatch.setattr(categorize, "_call_ai", _must_not_be_called)

    results, errors = await batch_categorize_with_ai(
        db, user_id,
        [{"id": "x", "merchant": "Some Unknown Shop", "description": "Some Unknown Shop", "amount": -10.0}],
    )

    assert results == []
    assert errors == ["AI categorization disabled or not configured"]


# ── load_ai_config: provider inference and usability ────────────────────

async def test_load_ai_config_infers_anthropic_when_api_key_set(db, user_id, monkeypatch):
    async def _fake_setting(db_arg, user_id_arg, key):
        return {"ai_api_key": "sk-test"}.get(key, "")

    monkeypatch.setattr(categorize, "get_setting", _fake_setting)

    config = await categorize.load_ai_config(db, user_id)
    assert config.provider == "anthropic"
    assert config.enabled is True


async def test_load_ai_config_infers_custom_when_endpoint_set(db, user_id, monkeypatch):
    async def _fake_setting(db_arg, user_id_arg, key):
        return {"ai_endpoint": "https://agent.example.com/categorize"}.get(key, "")

    monkeypatch.setattr(categorize, "get_setting", _fake_setting)

    config = await categorize.load_ai_config(db, user_id)
    assert config.provider == "custom"
    assert config.enabled is True


async def test_load_ai_config_openai_disabled_without_base_url(db, user_id, monkeypatch):
    async def _fake_setting(db_arg, user_id_arg, key):
        return {"ai_provider": "openai"}.get(key, "")

    monkeypatch.setattr(categorize, "get_setting", _fake_setting)

    config = await categorize.load_ai_config(db, user_id)
    assert config.provider == "openai"
    assert config.enabled is False


# ── _call_ai: provider dispatch ──────────────────────────────────────────

class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for httpx.AsyncClient."""

    def __init__(self, captured: list, response_json):
        self._captured = captured
        self._response_json = response_json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self._captured.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(self._response_json)


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


async def test_call_ai_openai_provider_parses_chat_completions_response(monkeypatch):
    captured: list = []
    response_json = {
        "choices": [{"message": {"content": '[{"m":"Migros","c":"Supermarket","s":0.9}]'}}]
    }
    monkeypatch.setattr(
        categorize.httpx, "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(captured, response_json),
    )

    config = categorize.AiConfig(
        enabled=True, provider="openai", api_key="sk-openai", model="gpt-4o-mini",
        endpoint="", auth_header="", base_url="http://localhost:11434/v1",
    )
    results, error = await categorize._call_ai(config, "prompt text", [{"id": "x"}])

    assert error is None
    assert results == [{"m": "Migros", "c": "Supermarket", "s": 0.9}]
    assert captured[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured[0]["headers"]["Authorization"] == "Bearer sk-openai"
    assert captured[0]["json"]["model"] == "gpt-4o-mini"


async def test_call_ai_custom_provider_sends_configured_model(monkeypatch):
    captured: list = []
    response_json = [{"m": "Migros", "c": "Supermarket", "s": 0.8}]
    monkeypatch.setattr(
        categorize.httpx, "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(captured, response_json),
    )

    config = categorize.AiConfig(
        enabled=True, provider="custom", api_key="", model="claude-opus-4",
        endpoint="https://agent.example.com/categorize", auth_header="Bearer secret",
        base_url="",
    )
    results, error = await categorize._call_ai(config, "prompt text", [{"id": "x"}])

    assert error is None
    assert results == response_json
    assert captured[0]["url"] == "https://agent.example.com/categorize"
    assert captured[0]["json"]["model"] == "claude-opus-4"  # not the old hardcoded default
    assert captured[0]["headers"]["Authorization"] == "Bearer secret"


async def test_call_ai_anthropic_provider_uses_async_client(monkeypatch):
    captured: list = []

    class _FakeContentBlock:
        def __init__(self, text):
            self.text = text

    class _FakeAnthropicResponse:
        def __init__(self, text):
            self.content = [_FakeContentBlock(text)]

    class _FakeMessages:
        async def create(self, **kwargs):
            captured.append(kwargs)
            return _FakeAnthropicResponse('[{"m":"Migros","c":"Supermarket","s":0.7}]')

    class _FakeAsyncAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.messages = _FakeMessages()

    monkeypatch.setattr(categorize.anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)

    config = categorize.AiConfig(
        enabled=True, provider="anthropic", api_key="sk-ant-test",
        model="claude-haiku-4-5-20251001", endpoint="", auth_header="", base_url="",
    )
    results, error = await categorize._call_ai(config, "prompt text", [{"id": "x"}])

    assert error is None
    assert results == [{"m": "Migros", "c": "Supermarket", "s": 0.7}]
    assert captured[0]["model"] == "claude-haiku-4-5-20251001"


# ── Confidence 0.0 must not be coerced to the 0.5 fallback ──────────────

def test_parse_ai_results_keeps_legitimate_zero_confidence():
    chunk = [{"id": "x", "merchant": "Unknown Shop"}]
    chunk_results = [{"m": "Unknown Shop", "c": "Other", "s": 0.0}]

    mapped = categorize._parse_ai_results(chunk_results, chunk, {"Other": "cat-other"})

    assert mapped[0]["confidence"] == 0.0


# ── Per-request custom rules are injected into the prompt ────────────────

def test_build_prompt_includes_custom_rules_with_priority():
    chunk = [{"id": "x", "merchant": "Migros", "amount": -20.0}]
    prompt = categorize._build_prompt("Groceries (Supermarket)", chunk, "Everything from Migros is Gaming")

    assert "Everything from Migros is Gaming" in prompt
    assert "priority" in prompt
    # Without custom rules the block is absent entirely
    assert "User rules" not in categorize._build_prompt("Groceries (Supermarket)", chunk)


def test_build_prompt_instructs_subcategory_over_parent_unambiguously():
    """A parent-only category name (e.g. "Finance", "Dining") must only be
    valid when that parent has no subcategories at all; models that default
    to the parent name despite subcategories being listed need this spelled
    out explicitly, not just "prefer subcategory"."""
    chunk = [{"id": "x", "merchant": "Migros", "amount": -20.0}]
    prompt = categorize._build_prompt("Groceries (Supermarket)", chunk)

    assert "SUBCATEGORY name whenever the parent has subcategories" in prompt
    assert "a parent name is only valid when it has no subcategories listed" in prompt


# ── _build_prompt: merchant context from web search ──────────────────────

def test_build_prompt_includes_merchant_context_when_provided():
    chunk = [{"id": "x", "merchant": "Some Cafe", "amount": -12.0}]
    context = {"Some Cafe": "Some Cafe official: a cozy coffee shop in Zurich"}

    prompt = categorize._build_prompt("Groceries (Supermarket)", chunk, merchant_context=context)

    assert "Merchant context from web search" in prompt
    assert "- Some Cafe: Some Cafe official: a cozy coffee shop in Zurich" in prompt


def test_build_prompt_omits_merchant_context_section_when_empty():
    chunk = [{"id": "x", "merchant": "Some Cafe", "amount": -12.0}]

    assert "Merchant context" not in categorize._build_prompt("Groceries (Supermarket)", chunk)
    assert "Merchant context" not in categorize._build_prompt(
        "Groceries (Supermarket)", chunk, merchant_context={}
    )


# ── _search_merchant_context: SearXNG enrichment, best-effort only ───────

def _client_with_transport(transport: httpx.MockTransport):
    def _factory(*args, **kwargs):
        kwargs["transport"] = transport
        return _RealAsyncClient(*args, **kwargs)
    return _factory


async def test_search_merchant_context_happy_path(monkeypatch):
    def handler(request):
        merchant = request.url.params.get("q")
        return httpx.Response(200, json={
            "results": [
                {"title": f"{merchant} Official Site", "content": "Coffee shop chain in Zurich"},
                {"title": f"{merchant} Reviews", "content": "Great coffee, friendly staff"},
                {"title": "Unrelated third result", "content": "Should be ignored"},
            ]
        })

    monkeypatch.setattr(
        categorize.httpx, "AsyncClient", _client_with_transport(httpx.MockTransport(handler))
    )

    result = await categorize._search_merchant_context(
        "http://searxng.local:8080", ["Starbucks", "Starbucks"]
    )

    assert list(result.keys()) == ["Starbucks"]  # de-duped
    assert "Starbucks Official Site: Coffee shop chain in Zurich" in result["Starbucks"]
    assert "Starbucks Reviews: Great coffee, friendly staff" in result["Starbucks"]
    assert "Unrelated third result" not in result["Starbucks"]  # only top 2


async def test_search_merchant_context_failure_yields_no_entry(monkeypatch):
    def handler(request):
        return httpx.Response(500)

    monkeypatch.setattr(
        categorize.httpx, "AsyncClient", _client_with_transport(httpx.MockTransport(handler))
    )

    result = await categorize._search_merchant_context("http://searxng.local:8080", ["Unknown Merchant"])

    assert result == {}


async def test_search_merchant_context_empty_results_yields_no_entry(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(
        categorize.httpx, "AsyncClient", _client_with_transport(httpx.MockTransport(handler))
    )

    result = await categorize._search_merchant_context("http://searxng.local:8080", ["Nobody Knows This"])

    assert result == {}


async def test_search_merchant_context_no_merchants_returns_empty_without_request(monkeypatch):
    def handler(request):
        raise AssertionError("should not be called")

    monkeypatch.setattr(
        categorize.httpx, "AsyncClient", _client_with_transport(httpx.MockTransport(handler))
    )

    result = await categorize._search_merchant_context("http://searxng.local:8080", [])

    assert result == {}
