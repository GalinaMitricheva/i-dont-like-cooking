import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from idlcooking.bot.handlers import bot_commands, router
from idlcooking.bot.i18n import DEFAULT_LANGUAGE
from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.config import get_settings
from idlcooking.scheduler import create_scheduler, register_scheduled_jobs


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot.")

    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=settings.telegram_bot_token)
    await bot.set_my_commands(
        [
            BotCommand(command=command, description=description)
            for command, description in bot_commands(DEFAULT_LANGUAGE)
        ]
    )
    planning_facade = TelegramPlanningFacade(settings.database_url)
    dispatcher = Dispatcher()
    dispatcher["planning_facade"] = planning_facade
    dispatcher.include_router(router)

    scheduler = create_scheduler()
    register_scheduled_jobs(scheduler, bot, planning_facade)
    scheduler.start()

    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
