from apscheduler.schedulers.asyncio import AsyncIOScheduler

from idlcooking.domain.schedule import PlanningSchedule


def create_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone=PlanningSchedule().timezone)
