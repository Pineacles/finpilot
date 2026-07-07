"""CRUD for reusable CSV column-mapping profiles (ImportProfile)."""
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_profile import ImportProfile


class ImportProfileNotFoundError(Exception):
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        super().__init__(f"Import profile not found: {profile_id}")


async def list_profiles(db: AsyncSession, user_id: str) -> list[ImportProfile]:
    result = await db.execute(
        select(ImportProfile).where(ImportProfile.user_id == user_id).order_by(ImportProfile.name)
    )
    return list(result.scalars().all())


async def create_profile(
    db: AsyncSession, user_id: str, name: str, account_id: str | None, mapping: dict
) -> ImportProfile:
    profile = ImportProfile(user_id=user_id, name=name, account_id=account_id, mapping=mapping)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_profile(db: AsyncSession, user_id: str, profile_id: str) -> ImportProfile:
    result = await db.execute(
        select(ImportProfile).where(and_(ImportProfile.id == profile_id, ImportProfile.user_id == user_id))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise ImportProfileNotFoundError(profile_id)
    return profile


async def delete_profile(db: AsyncSession, user_id: str, profile_id: str) -> None:
    profile = await get_profile(db, user_id, profile_id)
    await db.delete(profile)
    await db.commit()
