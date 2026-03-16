"""
Twilio ↔ DB Sync — periodic reconciliation of tracking numbers.

Runs every 15 minutes via APScheduler to catch drift between the
Twilio account and the DB (e.g. a release API call succeeded but
the DB update failed due to a crash or network blip).

Also exposes start_twilio_sync() for main.py lifespan startup.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import async_session
from app.core.models.connected_account import ConnectedAccount

logger = logging.getLogger(__name__)

SYNC_INTERVAL_MINUTES = 15
JOB_ID = "twilio_number_sync"


async def _run_sync():
    """Sync all businesses that have active Twilio credentials."""
    from app.admin.services.twilio_service import twilio_service

    async with async_session() as db:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.platform == "twilio",
            ConnectedAccount.status == "active",
        )
        result = await db.execute(stmt)
        accounts = result.scalars().all()

        if not accounts:
            return

        for account in accounts:
            try:
                sync_result = await twilio_service.sync_numbers(
                    db, account.business_id
                )
                if sync_result.get("deactivated"):
                    logger.info(
                        f"Twilio sync deactivated {len(sync_result['deactivated'])} "
                        f"numbers for business {account.business_id}"
                    )
            except Exception as e:
                logger.error(
                    f"Twilio sync error for business {account.business_id}: {e}"
                )

        await db.commit()


async def start_twilio_sync(scheduler: AsyncIOScheduler):
    """Register the interval job with the existing APScheduler instance."""
    scheduler.add_job(
        _run_sync,
        trigger=IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES),
        id=JOB_ID,
        name="Twilio ↔ DB number sync",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(
        f"Twilio number sync scheduled every {SYNC_INTERVAL_MINUTES} minutes"
    )
