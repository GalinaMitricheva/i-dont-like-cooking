from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade

router = Router()


def _telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram message has no user.")
    return message.from_user.id


def _resolve_message_language(message: Message) -> str:
    user = message.from_user
    return resolve_language(user.language_code if user else None)


@router.message(Command("start"))
async def start(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    planning_facade.ensure_user_defaults(_telegram_user_id(message), language=language)
    await message.answer(t(language, "start"))


@router.message(Command("plan"))
async def plan(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    command_text = message.text or ""
    inventory_text = command_text.removeprefix("/plan").strip()
    summary = planning_facade.generate_plan_from_text_inventory(
        _telegram_user_id(message),
        inventory_text=inventory_text,
    )
    menu = "\n".join(summary.menu_lines)
    shopping = "\n".join(summary.shopping_lines[:20])
    await message.answer(
        t(
            language,
            "plan",
            planning_cycle_id=summary.planning_cycle_id,
            menu=menu,
            shopping=shopping,
        )
    )


@router.message(Command("schedule"))
async def schedule(message: Message) -> None:
    language = _resolve_message_language(message)
    await message.answer(t(language, "schedule"))


@router.message(Command("profile"))
async def profile(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    summary = planning_facade.get_profile_summary(_telegram_user_id(message))
    await message.answer(
        t(
            language,
            "profile",
            household_size=summary.household_size,
            cooking_effort_minutes=summary.cooking_effort_minutes,
            planning_weekday=summary.planning_weekday,
            planning_time=summary.planning_time,
            timezone=summary.timezone,
        )
    )


@router.message(Command("fridge"))
async def fridge(message: Message) -> None:
    language = _resolve_message_language(message)
    await message.answer(t(language, "fridge"))
