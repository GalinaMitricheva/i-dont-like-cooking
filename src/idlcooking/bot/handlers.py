from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "Привет! Я помогу собрать простое меню на неделю и список покупок. "
        "Скоро здесь появится короткая анкета профиля."
    )


@router.message(Command("plan"))
async def plan(message: Message) -> None:
    await message.answer(
        "Пока я умею только готовить черновик плана в backend. "
        "Следующий шаг - связать Telegram с движком планирования."
    )


@router.message(Command("schedule"))
async def schedule(message: Message) -> None:
    await message.answer("Расписание по умолчанию: суббота, 09:00. Изменение расписания в работе.")


@router.message(Command("fridge"))
async def fridge(message: Message) -> None:
    await message.answer("Пришлите фото холодильника или напишите продукты текстом. Фото подключим через Ollama.")
