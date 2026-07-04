from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from idlcooking.bot.planning import TelegramPlanningFacade

router = Router()


def _telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram message has no user.")
    return message.from_user.id


@router.message(Command("start"))
async def start(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    user = message.from_user
    language = user.language_code if user and user.language_code else "ru"
    planning_facade.ensure_user_defaults(_telegram_user_id(message), language=language)
    await message.answer(
        "Привет! Я помогу собрать простое меню на неделю и список покупок.\n\n"
        "Можно начать с /plan. Если хочешь учесть продукты дома, напиши так:\n"
        "/plan рис, яйца, огурец"
    )


@router.message(Command("plan"))
async def plan(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    command_text = message.text or ""
    inventory_text = command_text.removeprefix("/plan").strip()
    summary = planning_facade.generate_plan_from_text_inventory(
        _telegram_user_id(message),
        inventory_text=inventory_text,
    )
    menu = "\n".join(summary.menu_lines)
    shopping = "\n".join(summary.shopping_lines[:20])
    await message.answer(
        f"Черновик меню #{summary.planning_cycle_id}:\n\n"
        f"{menu}\n\n"
        f"Список покупок:\n{shopping}"
    )


@router.message(Command("schedule"))
async def schedule(message: Message) -> None:
    await message.answer(
        "Расписание по умолчанию: суббота, 09:00. Изменение расписания подключим следующим шагом."
    )


@router.message(Command("fridge"))
async def fridge(message: Message) -> None:
    await message.answer(
        "Пока можно перечислить продукты текстом в команде /plan, например:\n"
        "/plan рис, яйца, огурец\n\n"
        "Фото холодильника подключим через локальный Ollama adapter."
    )
