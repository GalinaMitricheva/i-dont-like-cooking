from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    BudgetLevel,
    NutritionGoal,
    UserProfile,
)
from idlcooking.domain.schedule import parse_weekday

router = Router()

_DELETE_CONFIRM_CALLBACK = "delete_my_data:confirm"
_DELETE_CANCEL_CALLBACK = "delete_my_data:cancel"
_CONSENT_AGREE_CALLBACK = "consent:agree"
_CONSENT_DECLINE_CALLBACK = "consent:decline"
_COOKING_EFFORT_PREFIX = "onboarding:effort:"
_BUDGET_LEVEL_PREFIX = "onboarding:budget:"
_ACTIVITY_LEVEL_PREFIX = "onboarding:activity:"
_NUTRITION_GOAL_PREFIX = "onboarding:goal:"
_SEX_PREFIX = "onboarding:sex:"
_BODY_METRICS_YES = "onboarding:body_metrics:yes"
_BODY_METRICS_NO = "onboarding:body_metrics:no"


class OnboardingStates(StatesGroup):
    household_size = State()
    cooking_effort = State()
    allergies = State()
    hard_restrictions = State()
    disliked_ingredients = State()
    favorite_tags = State()
    budget_level = State()
    activity_level = State()
    nutrition_goal = State()
    body_metrics_choice = State()
    body_metrics_height = State()
    body_metrics_weight = State()
    body_metrics_age = State()
    body_metrics_sex = State()


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


def _enum_keyboard(
    language: str, prefix: str, options: tuple[tuple[str, str], ...]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, label_key), callback_data=f"{prefix}{value}")]
            for value, label_key in options
        ]
    )


def _cooking_effort_keyboard(language: str) -> InlineKeyboardMarkup:
    return _enum_keyboard(
        language,
        _COOKING_EFFORT_PREFIX,
        (
            ("5", "onboarding_effort_minimal"),
            ("15", "onboarding_effort_15"),
            ("30", "onboarding_effort_30"),
            ("60", "onboarding_effort_batch"),
        ),
    )


def _budget_level_keyboard(language: str) -> InlineKeyboardMarkup:
    return _enum_keyboard(
        language,
        _BUDGET_LEVEL_PREFIX,
        tuple((level.value, f"onboarding_budget_{level.value}") for level in BudgetLevel),
    )


def _activity_level_keyboard(language: str) -> InlineKeyboardMarkup:
    return _enum_keyboard(
        language,
        _ACTIVITY_LEVEL_PREFIX,
        tuple((level.value, f"onboarding_activity_{level.value}") for level in ActivityLevel),
    )


def _nutrition_goal_keyboard(language: str) -> InlineKeyboardMarkup:
    return _enum_keyboard(
        language,
        _NUTRITION_GOAL_PREFIX,
        tuple((goal.value, f"onboarding_goal_{goal.value}") for goal in NutritionGoal),
    )


def _body_metrics_choice_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "onboarding_body_metrics_yes"),
                    callback_data=_BODY_METRICS_YES,
                ),
                InlineKeyboardButton(
                    text=t(language, "onboarding_body_metrics_no"),
                    callback_data=_BODY_METRICS_NO,
                ),
            ]
        ]
    )


def _body_metrics_sex_keyboard(language: str) -> InlineKeyboardMarkup:
    return _enum_keyboard(
        language,
        _SEX_PREFIX,
        (("male", "onboarding_sex_male"), ("female", "onboarding_sex_female")),
    )


def _parse_list_answer(text: str) -> tuple[str, ...]:
    normalized = text.strip().lower()
    if normalized in {"none", "skip", "-"}:
        return ()
    return tuple(part.strip() for part in text.replace(";", ",").split(",") if part.strip())


async def _finish_onboarding(
    message: Message,
    planning_facade: TelegramPlanningFacade,
    state: FSMContext,
    telegram_user_id: int,
    language: str,
) -> None:
    data = await state.get_data()
    body_metrics = None
    if "body_metrics_height_cm" in data:
        body_metrics = BodyMetrics(
            height_cm=data["body_metrics_height_cm"],
            weight_kg=data["body_metrics_weight_kg"],
            age=data["body_metrics_age"],
            sex=data.get("body_metrics_sex", "unspecified"),
        )
    profile = UserProfile(
        household_size=data.get("household_size", 1),
        cooking_effort_minutes=data.get("cooking_effort_minutes", 20),
        allergies=tuple(data.get("allergies", ())),
        hard_restrictions=tuple(data.get("hard_restrictions", ())),
        disliked_ingredients=tuple(data.get("disliked_ingredients", ())),
        favorite_tags=tuple(data.get("favorite_tags", ())),
        budget_level=BudgetLevel(data.get("budget_level", BudgetLevel.MODERATE.value)),
        activity_level=ActivityLevel(data.get("activity_level", ActivityLevel.LIGHT.value)),
        nutrition_goal=NutritionGoal(data.get("nutrition_goal", NutritionGoal.MAINTAIN.value)),
        body_metrics=body_metrics,
    )
    planning_facade.save_profile(telegram_user_id, profile)
    await state.clear()
    await message.edit_text(t(language, "onboarding_complete"))


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
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    language = resolve_language(callback.from_user.language_code)
    if callback.data == _CONSENT_AGREE_CALLBACK:
        planning_facade.record_consent(callback.from_user.id, language=language)
        await state.set_state(OnboardingStates.household_size)
        await callback.message.edit_text(t(language, "onboarding_household_size_prompt"))
    else:
        await callback.message.edit_text(t(language, "consent_declined"))
    await callback.answer()


@router.message(OnboardingStates.household_size)
async def onboarding_household_size(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    value = (message.text or "").strip()
    if not value.isdigit() or not (1 <= int(value) <= 12):
        await message.answer(t(language, "onboarding_household_size_invalid"))
        return
    await state.update_data(household_size=int(value))
    await state.set_state(OnboardingStates.cooking_effort)
    await message.answer(
        t(language, "onboarding_cooking_effort_prompt"),
        reply_markup=_cooking_effort_keyboard(language),
    )


@router.callback_query(OnboardingStates.cooking_effort, F.data.startswith(_COOKING_EFFORT_PREFIX))
async def onboarding_cooking_effort(callback: CallbackQuery, state: FSMContext) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    minutes = int(callback.data.removeprefix(_COOKING_EFFORT_PREFIX))
    await state.update_data(cooking_effort_minutes=minutes)
    await state.set_state(OnboardingStates.allergies)
    await callback.message.edit_text(t(language, "onboarding_allergies_prompt"))
    await callback.answer()


@router.message(OnboardingStates.allergies)
async def onboarding_allergies(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    await state.update_data(allergies=_parse_list_answer(message.text or ""))
    await state.set_state(OnboardingStates.hard_restrictions)
    await message.answer(t(language, "onboarding_hard_restrictions_prompt"))


@router.message(OnboardingStates.hard_restrictions)
async def onboarding_hard_restrictions(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    await state.update_data(hard_restrictions=_parse_list_answer(message.text or ""))
    await state.set_state(OnboardingStates.disliked_ingredients)
    await message.answer(t(language, "onboarding_disliked_ingredients_prompt"))


@router.message(OnboardingStates.disliked_ingredients)
async def onboarding_disliked_ingredients(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    await state.update_data(disliked_ingredients=_parse_list_answer(message.text or ""))
    await state.set_state(OnboardingStates.favorite_tags)
    await message.answer(t(language, "onboarding_favorite_tags_prompt"))


@router.message(OnboardingStates.favorite_tags)
async def onboarding_favorite_tags(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    await state.update_data(favorite_tags=_parse_list_answer(message.text or ""))
    await state.set_state(OnboardingStates.budget_level)
    await message.answer(
        t(language, "onboarding_budget_level_prompt"),
        reply_markup=_budget_level_keyboard(language),
    )


@router.callback_query(OnboardingStates.budget_level, F.data.startswith(_BUDGET_LEVEL_PREFIX))
async def onboarding_budget_level(callback: CallbackQuery, state: FSMContext) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await state.update_data(budget_level=callback.data.removeprefix(_BUDGET_LEVEL_PREFIX))
    await state.set_state(OnboardingStates.activity_level)
    await callback.message.edit_text(
        t(language, "onboarding_activity_level_prompt"),
        reply_markup=_activity_level_keyboard(language),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.activity_level, F.data.startswith(_ACTIVITY_LEVEL_PREFIX))
async def onboarding_activity_level(callback: CallbackQuery, state: FSMContext) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await state.update_data(activity_level=callback.data.removeprefix(_ACTIVITY_LEVEL_PREFIX))
    await state.set_state(OnboardingStates.nutrition_goal)
    await callback.message.edit_text(
        t(language, "onboarding_nutrition_goal_prompt"),
        reply_markup=_nutrition_goal_keyboard(language),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.nutrition_goal, F.data.startswith(_NUTRITION_GOAL_PREFIX))
async def onboarding_nutrition_goal(callback: CallbackQuery, state: FSMContext) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await state.update_data(nutrition_goal=callback.data.removeprefix(_NUTRITION_GOAL_PREFIX))
    await state.set_state(OnboardingStates.body_metrics_choice)
    await callback.message.edit_text(
        t(language, "onboarding_body_metrics_choice_prompt"),
        reply_markup=_body_metrics_choice_keyboard(language),
    )
    await callback.answer()


@router.callback_query(
    OnboardingStates.body_metrics_choice, F.data.in_({_BODY_METRICS_YES, _BODY_METRICS_NO})
)
async def onboarding_body_metrics_choice(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    if callback.data == _BODY_METRICS_NO:
        await _finish_onboarding(
            callback.message, planning_facade, state, callback.from_user.id, language
        )
        await callback.answer()
        return
    await state.set_state(OnboardingStates.body_metrics_height)
    await callback.message.edit_text(t(language, "onboarding_body_metrics_height_prompt"))
    await callback.answer()


@router.message(OnboardingStates.body_metrics_height)
async def onboarding_body_metrics_height(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    value = (message.text or "").strip()
    if not value.isdigit():
        await message.answer(t(language, "onboarding_number_invalid"))
        return
    await state.update_data(body_metrics_height_cm=int(value))
    await state.set_state(OnboardingStates.body_metrics_weight)
    await message.answer(t(language, "onboarding_body_metrics_weight_prompt"))


@router.message(OnboardingStates.body_metrics_weight)
async def onboarding_body_metrics_weight(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    try:
        weight = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        weight = -1.0
    if weight <= 0:
        await message.answer(t(language, "onboarding_number_invalid"))
        return
    await state.update_data(body_metrics_weight_kg=weight)
    await state.set_state(OnboardingStates.body_metrics_age)
    await message.answer(t(language, "onboarding_body_metrics_age_prompt"))


@router.message(OnboardingStates.body_metrics_age)
async def onboarding_body_metrics_age(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    value = (message.text or "").strip()
    if not value.isdigit():
        await message.answer(t(language, "onboarding_number_invalid"))
        return
    await state.update_data(body_metrics_age=int(value))
    await state.set_state(OnboardingStates.body_metrics_sex)
    await message.answer(
        t(language, "onboarding_body_metrics_sex_prompt"),
        reply_markup=_body_metrics_sex_keyboard(language),
    )


@router.callback_query(OnboardingStates.body_metrics_sex, F.data.startswith(_SEX_PREFIX))
async def onboarding_body_metrics_sex(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await state.update_data(body_metrics_sex=callback.data.removeprefix(_SEX_PREFIX))
    await _finish_onboarding(
        callback.message, planning_facade, state, callback.from_user.id, language
    )
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
