from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.domain.schedule import parse_weekday

router = Router()

_DELETE_CONFIRM_CALLBACK = "delete_my_data:confirm"
_DELETE_CANCEL_CALLBACK = "delete_my_data:cancel"
_CONSENT_AGREE_CALLBACK = "consent:agree"
_CONSENT_DECLINE_CALLBACK = "consent:decline"


def _telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram message has no user.")
    return message.from_user.id


def _resolve_message_language(message: Message) -> str:
    user = message.from_user
    return resolve_language(user.language_code if user else None)


def _delete_confirmation_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "delete_my_data_confirm_button"),
                    callback_data=_DELETE_CONFIRM_CALLBACK,
                ),
                InlineKeyboardButton(
                    text=t(language, "delete_my_data_cancel_button"),
                    callback_data=_DELETE_CANCEL_CALLBACK,
                ),
            ]
        ]
    )


def _consent_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "consent_agree_button"),
                    callback_data=_CONSENT_AGREE_CALLBACK,
                ),
                InlineKeyboardButton(
                    text=t(language, "consent_decline_button"),
                    callback_data=_CONSENT_DECLINE_CALLBACK,
                ),
            ]
        ]
    )


async def _require_consent(
    message: Message, planning_facade: TelegramPlanningFacade, language: str
) -> bool:
    if planning_facade.has_user_consented(_telegram_user_id(message)):
        return True
    await message.answer(t(language, "consent_required"))
    return False


@router.message(Command("start"))
async def start(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if planning_facade.has_user_consented(_telegram_user_id(message)):
        await message.answer(t(language, "start"))
        return
    await message.answer(
        t(language, "consent_prompt"),
        reply_markup=_consent_keyboard(language),
    )


@router.callback_query(F.data.in_({_CONSENT_AGREE_CALLBACK, _CONSENT_DECLINE_CALLBACK}))
async def consent_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    language = resolve_language(callback.from_user.language_code)
    if callback.data == _CONSENT_AGREE_CALLBACK:
        planning_facade.record_consent(callback.from_user.id, language=language)
        await callback.message.edit_text(t(language, "start"))
    else:
        await callback.message.edit_text(t(language, "consent_declined"))
    await callback.answer()


@router.message(Command("plan"))
async def plan(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
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
async def schedule(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return

    telegram_user_id = _telegram_user_id(message)
    command_text = message.text or ""
    args = command_text.removeprefix("/schedule").strip()

    if not args:
        summary = planning_facade.get_schedule_summary(telegram_user_id)
        await message.answer(
            t(
                language,
                "schedule_current",
                weekday_name=summary.weekday_name,
                at_time=summary.at_time,
                timezone=summary.timezone,
            )
        )
        return

    parts = args.split()
    if len(parts) not in (2, 3):
        await message.answer(t(language, "schedule_usage"))
        return

    weekday_token, time_token, *timezone_parts = parts
    timezone_name = (
        timezone_parts[0]
        if timezone_parts
        else planning_facade.get_schedule_summary(telegram_user_id).timezone
    )

    try:
        weekday = parse_weekday(weekday_token)
        at_time = datetime.strptime(time_token, "%H:%M").time()
        ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        await message.answer(t(language, "schedule_invalid"))
        return

    summary = planning_facade.update_schedule(
        telegram_user_id,
        weekday=weekday,
        at_time=at_time,
        timezone=timezone_name,
    )
    await message.answer(
        t(
            language,
            "schedule_updated",
            weekday_name=summary.weekday_name,
            at_time=summary.at_time,
            timezone=summary.timezone,
        )
    )


@router.message(Command("profile"))
async def profile(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
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


@router.message(Command("delete_my_data"))
async def delete_my_data(message: Message) -> None:
    language = _resolve_message_language(message)
    await message.answer(
        t(language, "delete_my_data_confirm"),
        reply_markup=_delete_confirmation_keyboard(language),
    )


@router.callback_query(F.data.in_({_DELETE_CONFIRM_CALLBACK, _DELETE_CANCEL_CALLBACK}))
async def delete_my_data_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    language = resolve_language(callback.from_user.language_code)
    if callback.data == _DELETE_CONFIRM_CALLBACK:
        planning_facade.delete_user_data(callback.from_user.id)
        await callback.message.edit_text(t(language, "delete_my_data_done"))
    else:
        await callback.message.edit_text(t(language, "delete_my_data_cancelled"))
    await callback.answer()
