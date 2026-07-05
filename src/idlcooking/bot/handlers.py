from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade, TelegramRecipeDetail
from idlcooking.domain.feedback import CookedStatus, Rating, RecipeFeedback
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
_FEEDBACK_PREFIX = "feedback:"
_PLAN_ACCEPT_CALLBACK = "plan:accept"
_PLAN_REGENERATE_CALLBACK = "plan:regenerate"
_PLAN_SHOPPING_LIST_CALLBACK = "plan:shopping_list"
_PLAN_RATE_CALLBACK = "plan:rate"
_PLAN_MEALS_PREFIX = "plan:meals:"
_PLAN_RECIPES_CALLBACK = "plan:recipes"
_RECIPE_VIEW_PREFIX = "plan:recipe_view:"
_PLAN_BACK_TO_MENU_CALLBACK = "plan:back_to_menu"
_PLAN_BACK_TO_DAYS_CALLBACK = "plan:back_to_days"
_FEEDBACK_BACK_CALLBACK = "feedback:back"
_FEEDBACK_START_PREFIX = "feedback:start:"

# Telegram-length safety cap on the inline shopping list; the full list is always
# available via /currentplan.
_MAX_SHOPPING_LINES = 30

# Command names shared between /help and the Telegram native command menu
# (Bot.set_my_commands in bot/main.py), so the two can never drift apart.
_COMMAND_NAMES: tuple[str, ...] = (
    "start",
    "plan",
    "currentplan",
    "schedule",
    "profile",
    "feedback",
    "fridge",
    "help",
    "delete_my_data",
)

_FEEDBACK_CHOICES: dict[str, tuple[CookedStatus, Rating, str | None, str | None]] = {
    "liked": (CookedStatus.COOKED, Rating.LIKED, None, None),
    "neutral": (CookedStatus.COOKED, Rating.NEUTRAL, None, None),
    "too_much_effort": (CookedStatus.COOKED, Rating.DISLIKED, "too_much_effort", None),
    "too_expensive": (CookedStatus.COOKED, Rating.NEUTRAL, None, "too_expensive"),
    "skipped": (CookedStatus.SKIPPED, Rating.NEUTRAL, None, None),
}


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


class FeedbackStates(StatesGroup):
    reviewing = State()


class PlanStates(StatesGroup):
    days = State()
    meals = State()


def bot_commands(language: str) -> tuple[tuple[str, str], ...]:
    """Command name/description pairs, shared by /help and Bot.set_my_commands."""
    return tuple((command, t(language, f"help_cmd_{command}")) for command in _COMMAND_NAMES)


def _terminal_text(language: str, text: str, *, has_keyboard: bool) -> str:
    """Ensure a terminal bot response always points somewhere further (issue #20).

    Several handlers used to send a final message with no keyboard and no mention of
    what to do next, leaving the conversation at a dead end. Routing a terminal
    response's text through this helper means a new handler has to explicitly pass
    `has_keyboard=True` (because it attached a relevant keyboard) to opt out of the
    generic "/help" pointer, rather than silently omitting both.
    """
    if has_keyboard:
        return text
    return f"{text}\n\n{t(language, 'help_hint')}"


def _back_only_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_back_to_menu_button(language)]])


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


def _feedback_keyboard(language: str, *, show_back: bool) -> InlineKeyboardMarkup:
    """Rating prompt keyboard.

    Every prompt — including the very first (issue #33) — carries a "Back to menu" exit
    so the user is never trapped in the rating flow. The "Previous meal" step-back is a
    separate affordance shown only once past the first meal (`show_back`).
    """
    rows = [
        [
            InlineKeyboardButton(
                text=t(language, "feedback_liked_button"),
                callback_data=f"{_FEEDBACK_PREFIX}liked",
            ),
            InlineKeyboardButton(
                text=t(language, "feedback_neutral_button"),
                callback_data=f"{_FEEDBACK_PREFIX}neutral",
            ),
        ],
        [
            InlineKeyboardButton(
                text=t(language, "feedback_too_much_effort_button"),
                callback_data=f"{_FEEDBACK_PREFIX}too_much_effort",
            ),
            InlineKeyboardButton(
                text=t(language, "feedback_too_expensive_button"),
                callback_data=f"{_FEEDBACK_PREFIX}too_expensive",
            ),
        ],
        [
            InlineKeyboardButton(
                text=t(language, "feedback_skipped_button"),
                callback_data=f"{_FEEDBACK_PREFIX}skipped",
            ),
        ],
    ]
    nav_row = []
    if show_back:
        nav_row.append(
            InlineKeyboardButton(
                text=t(language, "feedback_previous_meal_button"),
                callback_data=_FEEDBACK_BACK_CALLBACK,
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            text=t(language, "feedback_back_to_menu_button"),
            callback_data=_PLAN_BACK_TO_MENU_CALLBACK,
        )
    )
    rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_keyboard(language: str, *, accepted: bool) -> InlineKeyboardMarkup:
    """Build the plan's keyboard for its current state (issues #23, #27).

    A draft can still be accepted, regenerated, or rated, is rated only once accepted,
    since rating meals that haven't been cooked yet doesn't make sense. Accept and
    Regenerate disappear once accepted since they no longer apply to a settled plan.
    """
    rows = []
    if not accepted:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(language, "plan_accept_button"),
                    callback_data=_PLAN_ACCEPT_CALLBACK,
                ),
                InlineKeyboardButton(
                    text=t(language, "plan_regenerate_button"),
                    callback_data=_PLAN_REGENERATE_CALLBACK,
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t(language, "plan_shopping_list_button"),
                callback_data=_PLAN_SHOPPING_LIST_CALLBACK,
            ),
            InlineKeyboardButton(
                text=t(language, "plan_recipes_button"),
                callback_data=_PLAN_RECIPES_CALLBACK,
            ),
        ]
    )
    if accepted:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(language, "plan_rate_button"),
                    callback_data=_PLAN_RATE_CALLBACK,
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_to_menu_button(language: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=t(language, "back_button"),
        callback_data=_PLAN_BACK_TO_MENU_CALLBACK,
    )


def _recipe_view_keyboard(language: str, day_index: int, total_days: int) -> InlineKeyboardMarkup:
    nav_row = []
    if day_index > 0:
        nav_row.append(
            InlineKeyboardButton(
                text=t(language, "recipe_view_previous_button"),
                callback_data=f"{_RECIPE_VIEW_PREFIX}{day_index - 1}",
            )
        )
    if day_index < total_days - 1:
        nav_row.append(
            InlineKeyboardButton(
                text=t(language, "recipe_view_next_button"),
                callback_data=f"{_RECIPE_VIEW_PREFIX}{day_index + 1}",
            )
        )
    rows = [nav_row] if nav_row else []
    rows.append([_back_to_menu_button(language)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_MEAL_CHOICES: dict[str, tuple[bool, bool]] = {
    # choice -> (include_dinner_leftovers, include_breakfast)
    "lunch_only": (False, False),
    "lunch_and_breakfast": (False, True),
    "lunch_and_dinner": (True, False),
    "lunch_dinner_breakfast": (True, True),
}


def _plan_meals_keyboard(language: str) -> InlineKeyboardMarkup:
    keyboard = _enum_keyboard(
        language,
        _PLAN_MEALS_PREFIX,
        (
            ("lunch_only", "plan_meals_lunch_only"),
            ("lunch_and_breakfast", "plan_meals_lunch_and_breakfast"),
            ("lunch_and_dinner", "plan_meals_lunch_and_dinner"),
            ("lunch_dinner_breakfast", "plan_meals_all"),
        ),
    )
    keyboard.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=t(language, "back_button"), callback_data=_PLAN_BACK_TO_DAYS_CALLBACK
            )
        ]
    )
    return keyboard


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


def _plan_body_text(language: str, menu: str, *, accepted: bool) -> str:
    """Plan message body, matching the keyboard's draft/accepted state (issue #32).

    An accepted plan must not keep reading as a "draft", so the wording is chosen from
    the same acceptance flag the keyboard uses rather than being hardcoded.
    """
    return t(language, "plan_accepted" if accepted else "plan", menu=menu)


async def _send_plan(
    message: Message,
    summary_menu_lines: tuple[str, ...],
    language: str,
) -> None:
    # A freshly generated or regenerated plan is always an unaccepted draft.
    await message.answer(
        _plan_body_text(language, "\n".join(summary_menu_lines), accepted=False),
        reply_markup=plan_keyboard(language, accepted=False),
    )


@router.message(Command("plan"))
async def plan(
    message: Message, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
    command_text = message.text or ""
    inventory_text = command_text.removeprefix("/plan").strip()
    await state.update_data(plan_inventory_text=inventory_text)
    await state.set_state(PlanStates.days)
    await message.answer(t(language, "plan_days_prompt"))


@router.message(PlanStates.days)
async def plan_days_message(message: Message, state: FSMContext) -> None:
    language = _resolve_message_language(message)
    value = (message.text or "").strip()
    if not value.isdigit() or not (1 <= int(value) <= 7):
        await message.answer(t(language, "plan_days_invalid"))
        return
    await state.update_data(plan_days=int(value))
    await state.set_state(PlanStates.meals)
    await message.answer(
        t(language, "plan_meals_prompt"),
        reply_markup=_plan_meals_keyboard(language),
    )


@router.callback_query(PlanStates.meals, F.data == _PLAN_BACK_TO_DAYS_CALLBACK)
async def plan_meals_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await state.set_state(PlanStates.days)
    await callback.message.edit_text(t(language, "plan_days_prompt"))
    await callback.answer()


@router.callback_query(PlanStates.meals, F.data.startswith(_PLAN_MEALS_PREFIX))
async def plan_meals_callback(
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
    choice = callback.data.removeprefix(_PLAN_MEALS_PREFIX)
    include_dinner_leftovers, include_breakfast = _MEAL_CHOICES.get(choice, (True, False))
    await state.update_data(
        plan_include_dinner_leftovers=include_dinner_leftovers,
        plan_include_breakfast=include_breakfast,
    )

    data = await state.get_data()
    summary = planning_facade.generate_plan_from_text_inventory(
        callback.from_user.id,
        inventory_text=data.get("plan_inventory_text", ""),
        include_dinner_leftovers=include_dinner_leftovers,
        include_breakfast=include_breakfast,
        days=data.get("plan_days", 7),
    )
    # Exit the flow but keep the chosen settings so "Regenerate" can reuse them.
    await state.set_state(None)
    await _send_plan(callback.message, summary.menu_lines, language)
    await callback.answer()


@router.callback_query(F.data == _PLAN_ACCEPT_CALLBACK)
async def plan_accept_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    if planning_facade.accept_latest_cycle(callback.from_user.id):
        # Reflect acceptance in the message text *and* the keyboard (issues #27, #32):
        # rewrite the body so an accepted plan no longer reads as a "draft", not just
        # swap the buttons. Fall back to a keyboard-only edit if the menu can't be
        # rebuilt for some reason.
        summary = planning_facade.get_latest_plan_summary(callback.from_user.id)
        accepted_keyboard = plan_keyboard(language, accepted=True)
        if summary is not None:
            await callback.message.edit_text(
                _plan_body_text(language, "\n".join(summary.menu_lines), accepted=True),
                reply_markup=accepted_keyboard,
            )
        else:
            await callback.message.edit_reply_markup(reply_markup=accepted_keyboard)
    await callback.answer(t(language, "plan_accepted_toast"))


@router.callback_query(F.data == _PLAN_REGENERATE_CALLBACK)
async def plan_regenerate_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    data = await state.get_data()
    summary = planning_facade.generate_plan_from_text_inventory(
        callback.from_user.id,
        inventory_text=data.get("plan_inventory_text", ""),
        include_dinner_leftovers=data.get("plan_include_dinner_leftovers", True),
        include_breakfast=data.get("plan_include_breakfast", False),
        days=data.get("plan_days", 7),
    )
    await _send_plan(callback.message, summary.menu_lines, language)
    await callback.answer()


def _truncate_shopping_lines(
    language: str, lines: tuple[str, ...], max_lines: int
) -> tuple[str, ...]:
    """Trim the formatted shopping list to at most `max_lines` without orphaning a header.

    A flat ``lines[:max_lines]`` slice can cut right after a category header (or between a
    header and its only item), leaving a dangling "Protein:" with nothing beneath it and
    silently dropping needed items (issue #31). Instead we cut at an item boundary, drop
    any now-trailing header/blank lines, and note how many items were left off.
    """
    total_items = sum(1 for line in lines if line.startswith("- "))
    if len(lines) <= max_lines:
        return lines
    # Reserve one line for the "…and N more" note.
    kept = list(lines[: max_lines - 1])
    while kept and (kept[-1].endswith(":") or not kept[-1].strip()):
        kept.pop()
    remaining = total_items - sum(1 for line in kept if line.startswith("- "))
    if remaining > 0:
        kept.append(t(language, "plan_shopping_list_more", count=remaining))
    return tuple(kept)


@router.callback_query(F.data == _PLAN_SHOPPING_LIST_CALLBACK)
async def plan_shopping_list_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    lines = planning_facade.get_latest_shopping_list_lines(callback.from_user.id)
    if not lines:
        await callback.answer(t(language, "plan_no_shopping_list"), show_alert=True)
        return
    shopping = "\n".join(_truncate_shopping_lines(language, lines, _MAX_SHOPPING_LINES))
    await callback.message.answer(
        t(language, "plan_shopping_list", shopping=shopping),
        reply_markup=_back_only_keyboard(language),
    )
    await callback.answer()


def _format_day_recipes(
    language: str, day_index: int, items: list[TelegramRecipeDetail]
) -> str:
    lines = [t(language, "recipe_view_day_header", day=day_index + 1)]
    for item in items:
        lines.append("")
        if item.is_leftover:
            detail = f"leftover {item.title} ({item.active_time_minutes} min)"
        elif item.servings is not None:
            detail = f"{item.title} ({item.active_time_minutes} min, makes {item.servings})"
        else:
            detail = f"{item.title} ({item.active_time_minutes} min)"
        lines.append(f"{item.meal_type.capitalize()}: {detail}")
        if item.ingredients:
            lines.append("Ingredients: " + ", ".join(item.ingredients))
        if item.steps_summary:
            lines.append(item.steps_summary)
        lines.append(f"Source: {item.source_url}")
    return "\n".join(lines)


async def _show_recipe_day(
    message: Message,
    planning_facade: TelegramPlanningFacade,
    telegram_user_id: int,
    day_index: int,
    language: str,
    *,
    edit: bool,
) -> None:
    days = planning_facade.get_latest_recipe_details_by_day(telegram_user_id)
    if not days:
        await message.answer(t(language, "plan_no_recipes"))
        return
    day_index = max(0, min(day_index, len(days) - 1))
    text = _format_day_recipes(language, day_index, days[day_index])
    keyboard = _recipe_view_keyboard(language, day_index, len(days))
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == _PLAN_RECIPES_CALLBACK)
async def plan_recipes_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    await _show_recipe_day(
        callback.message, planning_facade, callback.from_user.id, 0, language, edit=False
    )
    await callback.answer()


@router.callback_query(F.data.startswith(_RECIPE_VIEW_PREFIX))
async def recipe_view_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade
) -> None:
    if (
        callback.from_user is None
        or not isinstance(callback.message, Message)
        or callback.data is None
    ):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    day_index = int(callback.data.removeprefix(_RECIPE_VIEW_PREFIX))
    await _show_recipe_day(
        callback.message, planning_facade, callback.from_user.id, day_index, language, edit=True
    )
    await callback.answer()


@router.callback_query(F.data == _PLAN_BACK_TO_MENU_CALLBACK)
async def plan_back_to_menu_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    # If the user tapped "Back to menu" mid-rating (issue #33), leave the feedback FSM
    # so they aren't stuck in it. Only the state marker is cleared — any other state
    # data (e.g. the plan settings that Regenerate reuses) is left intact.
    if await state.get_state() == FeedbackStates.reviewing.state:
        await state.set_state(None)
    summary = planning_facade.get_latest_plan_summary(callback.from_user.id)
    if summary is None:
        await callback.answer(t(language, "plan_no_recipes"), show_alert=True)
        return
    menu = "\n".join(summary.menu_lines)
    accepted = planning_facade.is_latest_cycle_accepted(callback.from_user.id)
    # Match the wording to acceptance state (issue #32) the same way the keyboard does,
    # so navigating back to an accepted menu doesn't relabel it a "draft".
    await callback.message.edit_text(
        _plan_body_text(language, menu, accepted=accepted),
        reply_markup=plan_keyboard(language, accepted=accepted),
    )
    await callback.answer()


@router.callback_query(F.data == _PLAN_RATE_CALLBACK)
async def plan_rate_callback(
    callback: CallbackQuery, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    # Defensive check (issue #23): the keyboard already hides this button on drafts,
    # but a stale keyboard on an older message could still surface this callback.
    if not planning_facade.is_latest_cycle_accepted(callback.from_user.id):
        await callback.answer(t(language, "plan_not_accepted_yet_toast"), show_alert=True)
        return
    await _start_feedback_flow(
        callback.message, planning_facade, state, callback.from_user.id, language
    )
    await callback.answer()


@router.message(Command("currentplan"))
async def current_plan(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
    status = planning_facade.get_current_plan_status(_telegram_user_id(message))
    if status is None:
        await message.answer(
            _terminal_text(language, t(language, "current_plan_none"), has_keyboard=False)
        )
        return

    menu = "\n".join(status.menu_lines)
    next_planning = status.next_planning_at or t(language, "current_plan_next_unknown")
    if status.not_started:
        template = "current_plan_not_started"
    elif status.plan_complete:
        template = "current_plan_complete"
    else:
        template = "current_plan"
    text = t(
        language,
        template,
        current_day=status.current_day,
        total_days=status.total_days,
        menu=menu,
        next_planning=next_planning,
    )
    # Reuse the accepted-plan keyboard so shopping list / recipes / rate are one tap away.
    await message.answer(text, reply_markup=plan_keyboard(language, accepted=True))


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
    # Tolerate the exact form the bot displays back to the user, e.g. the timezone
    # shown as "(Europe/Berlin)" and a weekday copied with a trailing comma — otherwise
    # pasting the summary straight back fails (issue #34).
    weekday_token = weekday_token.strip(" ,")
    timezone_name = (
        timezone_parts[0].strip(" ()")
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
        _terminal_text(
            language,
            t(
                language,
                "schedule_updated",
                weekday_name=summary.weekday_name,
                at_time=summary.at_time,
                timezone=summary.timezone,
            ),
            has_keyboard=False,
        )
    )


@router.message(Command("profile"))
async def profile(message: Message, planning_facade: TelegramPlanningFacade) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
    summary = planning_facade.get_profile_summary(_telegram_user_id(message))
    await message.answer(
        _terminal_text(
            language,
            t(
                language,
                "profile",
                household_size=summary.household_size,
                cooking_effort_minutes=summary.cooking_effort_minutes,
                planning_weekday=summary.planning_weekday,
                planning_time=summary.planning_time,
                timezone=summary.timezone,
            ),
            has_keyboard=False,
        )
    )


async def _send_next_feedback_prompt(message: Message, state: FSMContext, language: str) -> None:
    data = await state.get_data()
    items: list[dict[str, str]] = data["feedback_items"]
    index: int = data["feedback_index"]

    if index >= len(items):
        await state.clear()
        await message.answer(
            t(language, "feedback_complete"), reply_markup=_back_only_keyboard(language)
        )
        return

    await message.answer(
        t(language, "feedback_prompt", title=items[index]["title"]),
        reply_markup=_feedback_keyboard(language, show_back=index > 0),
    )


async def _start_feedback_flow(
    message: Message,
    planning_facade: TelegramPlanningFacade,
    state: FSMContext,
    telegram_user_id: int,
    language: str,
    planning_cycle_id: int | None = None,
) -> None:
    # A scheduled feedback request (issue #37) targets a specific cycle; /feedback and the
    # post-acceptance Rate button default to whatever the latest cycle is.
    if planning_cycle_id is None:
        targets = planning_facade.get_latest_cycle_feedback_targets(telegram_user_id)
    else:
        targets = planning_facade.get_cycle_feedback_targets(telegram_user_id, planning_cycle_id)
    if targets is None or not targets[1]:
        await message.answer(t(language, "feedback_no_cycle"))
        return

    planning_cycle_id, items = targets
    await state.set_state(FeedbackStates.reviewing)
    await state.update_data(
        feedback_planning_cycle_id=planning_cycle_id,
        feedback_items=[{"title": item.title, "source_url": item.source_url} for item in items],
        feedback_index=0,
    )
    await _send_next_feedback_prompt(message, state, language)


def feedback_request_keyboard(language: str, planning_cycle_id: int) -> InlineKeyboardMarkup:
    """One-tap entry into rating a specific cycle, used by the scheduled request (issue #37)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "plan_rate_button"),
                    callback_data=f"{_FEEDBACK_START_PREFIX}{planning_cycle_id}",
                )
            ]
        ]
    )


@router.message(Command("feedback"))
async def feedback(
    message: Message, planning_facade: TelegramPlanningFacade, state: FSMContext
) -> None:
    language = _resolve_message_language(message)
    if not await _require_consent(message, planning_facade, language):
        return
    telegram_user_id = _telegram_user_id(message)
    await _start_feedback_flow(message, planning_facade, state, telegram_user_id, language)


@router.callback_query(F.data.startswith(_FEEDBACK_START_PREFIX))
async def feedback_start_callback(
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
    try:
        planning_cycle_id = int(callback.data.removeprefix(_FEEDBACK_START_PREFIX))
    except ValueError:
        await callback.answer()
        return
    await _start_feedback_flow(
        callback.message,
        planning_facade,
        state,
        callback.from_user.id,
        language,
        planning_cycle_id=planning_cycle_id,
    )
    await callback.answer()


@router.callback_query(FeedbackStates.reviewing, F.data == _FEEDBACK_BACK_CALLBACK)
async def feedback_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    language = resolve_language(callback.from_user.language_code)
    data = await state.get_data()
    index = max(0, data.get("feedback_index", 0) - 1)
    await state.update_data(feedback_index=index)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _send_next_feedback_prompt(callback.message, state, language)
    await callback.answer()


@router.callback_query(FeedbackStates.reviewing, F.data.startswith(_FEEDBACK_PREFIX))
async def feedback_callback(
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
    choice = callback.data.removeprefix(_FEEDBACK_PREFIX)
    data = await state.get_data()
    items: list[dict[str, str]] = data["feedback_items"]
    index: int = data["feedback_index"]
    item = items[index]

    cooked_status, rating, effort_feedback, cost_feedback = _FEEDBACK_CHOICES[choice]
    planning_facade.record_feedback(
        callback.from_user.id,
        data["feedback_planning_cycle_id"],
        RecipeFeedback(
            recipe_source_url=item["source_url"],
            recipe_title=item["title"],
            cooked_status=cooked_status,
            rating=rating,
            effort_feedback=effort_feedback,
            cost_feedback=cost_feedback,
        ),
    )
    await state.update_data(feedback_index=index + 1)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _send_next_feedback_prompt(callback.message, state, language)
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    language = _resolve_message_language(message)
    commands_text = "\n".join(
        f"/{command} — {description}" for command, description in bot_commands(language)
    )
    await message.answer(t(language, "help", commands=commands_text))


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
        await callback.message.edit_text(
            _terminal_text(language, t(language, "delete_my_data_cancelled"), has_keyboard=False)
        )
    await callback.answer()
