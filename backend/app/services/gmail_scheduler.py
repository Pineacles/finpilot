"""Background scheduler for Gmail polling.

Checks each user's gmail_poll_interval setting and polls accordingly.
Runs as an asyncio background task started with the FastAPI app.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_

from app.core.database import async_session
from app.models.user import User
from app.models.settings import UserSetting
from app.services.gmail_poller import poll_gmail

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _poll_loop():
    """Main polling loop. Checks every 60 seconds which users need polling."""
    logger.info("Gmail auto-poll scheduler started")
    # Track last poll time per user
    last_polled: dict[str, datetime] = {}

    while True:
        try:
            await asyncio.sleep(60)  # Check every minute

            async with async_session() as db:
                # Find users with gmail configured and a poll interval > 0
                result = await db.execute(
                    select(UserSetting.user_id, UserSetting.value)
                    .where(UserSetting.key == "gmail_poll_interval")
                )
                intervals = {r[0]: r[1] for r in result.all()}

                for user_id, interval_str in intervals.items():
                    try:
                        interval_min = int(interval_str)
                    except (ValueError, TypeError):
                        continue

                    if interval_min <= 0:
                        continue

                    # Check if enough time has passed
                    now = datetime.now(timezone.utc)
                    last = last_polled.get(user_id)
                    if last and (now - last).total_seconds() < interval_min * 60:
                        continue

                    # Check gmail is actually configured
                    addr_result = await db.execute(
                        select(UserSetting.value).where(and_(
                            UserSetting.user_id == user_id,
                            UserSetting.key == "gmail_address",
                        ))
                    )
                    addr = addr_result.scalar()
                    if not addr:
                        continue

                    # Poll
                    logger.info(f"Auto-polling Gmail for user {user_id[:8]}...")
                    result = await poll_gmail(db, user_id)
                    last_polled[user_id] = now

                    if result["new_transactions"] > 0:
                        logger.info(f"Gmail auto-poll: {result['new_transactions']} new, balance={result['balance']}")

        except Exception as e:
            logger.error(f"Gmail scheduler error: {e}", exc_info=True)
            await asyncio.sleep(30)


def start_scheduler():
    """Start the background polling task."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_poll_loop())
        logger.info("Gmail scheduler task created")


def stop_scheduler():
    """Stop the background polling task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None
