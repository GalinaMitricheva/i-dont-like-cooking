import logging
from datetime import UTC, datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from idlcooking.bot.handlers import plan_keyboard
from idlcooking.bot.i18n import t
from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.domain.schedule import PlanningSchedule

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 5
JOB_ID = "weekly_planning_cycles"


def create_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone=PlanningSchedule().timezone)


async def run_due_planning_cycles(bot: Bot, planning_facade: TelegramPlanningFacade) -> None:
    now = datetime.now(UTC)
    for telegram_user_id in planning_facade.get_due_telegram_user_ids(now):
        try:
            summary = planning_facade.generate_plan_from_text_inventory(telegram_user_id)
            language = planning_facade.get_language(telegram_user_id)
            menu = "\n".join(summary.menu_lines)
            await bot.send_message(
                telegram_user_id,
                t(language, "plan", menu=menu),
                reply_markup=plan_keyboard(language, accepted=False),
            )
            planning_facade.mark_schedule_triggered(telegram_user_id, now)
        except Exception:
            logger.exception(
                "Failed to run scheduled planning cycle for telegram user %s", telegram_user_id
            )


def register_scheduled_jobs(
    scheduler: AsyncIOScheduler, bot: Bot, planning_facade: TelegramPlanningFacade
) -> None:
    scheduler.add_job(
        run_due_planning_cycles,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=(bot, planning_facade),
        id=JOB_ID,
        replace_existing=True,
    )
