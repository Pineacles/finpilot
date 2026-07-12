"""ImportProfile CRUD: per-user scoping for saved CSV column mappings."""
from __future__ import annotations

import pytest

from app.services import import_profile_service
from app.services.import_profile_service import ImportProfileNotFoundError


SAMPLE_MAPPING = {
    "date_col": "Datum", "amount_col": "Betrag", "description_col": "Text",
    "date_format": "%d.%m.%Y", "decimal_separator": ".", "invert_amount": False, "currency": "CHF",
}


async def test_create_and_list_profiles(db, user_id):
    created = await import_profile_service.create_profile(db, user_id, "Cumulus Export", None, SAMPLE_MAPPING)
    assert created.name == "Cumulus Export"
    assert created.mapping["date_col"] == "Datum"

    listed = await import_profile_service.list_profiles(db, user_id)
    assert len(listed) == 1
    assert listed[0].id == created.id


async def test_profiles_scoped_per_user(db, user_id):
    await import_profile_service.create_profile(db, user_id, "Mine", None, SAMPLE_MAPPING)
    await import_profile_service.create_profile(db, "other-user", "Theirs", None, SAMPLE_MAPPING)

    mine = await import_profile_service.list_profiles(db, user_id)
    assert [p.name for p in mine] == ["Mine"]


async def test_delete_profile(db, user_id):
    created = await import_profile_service.create_profile(db, user_id, "Temp", None, SAMPLE_MAPPING)
    await import_profile_service.delete_profile(db, user_id, created.id)
    assert await import_profile_service.list_profiles(db, user_id) == []


async def test_delete_profile_not_found_raises(db, user_id):
    with pytest.raises(ImportProfileNotFoundError):
        await import_profile_service.delete_profile(db, user_id, "does-not-exist")


async def test_delete_profile_scoped_to_owner(db, user_id):
    created = await import_profile_service.create_profile(db, "other-user", "Theirs", None, SAMPLE_MAPPING)
    with pytest.raises(ImportProfileNotFoundError):
        await import_profile_service.delete_profile(db, user_id, created.id)
    # Still there
    assert len(await import_profile_service.list_profiles(db, "other-user")) == 1
