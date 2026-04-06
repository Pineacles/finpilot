"""Seed script: creates a default user with API key."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, engine, Base
from app.core.security import hash_password, generate_api_key
from app.models.user import User
from app.models.account import Account


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == "user@example.com"))
        if result.scalar_one_or_none():
            print("Seed user already exists, skipping.")
            return

        api_key = generate_api_key()
        user = User(
            email="user@example.com",
            password_hash=hash_password("change-me"),
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

        print(f"Seed user created: user@example.com / change-me")
        print(f"API Key: {api_key}")


if __name__ == "__main__":
    asyncio.run(seed())
