from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

from idlcooking.bot.handlers import (
    _PLAN_ACCEPT_CALLBACK,
    _PLAN_BACK_TO_MENU_CALLBACK,
    _PLAN_RATE_CALLBACK,
    _PLAN_REGENERATE_CALLBACK,
    _back_only_keyboard,
    _parse_list_answer,
    _resolve_message_language,
    _terminal_text,
    bot_commands,
    plan_keyboard,
)
from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.domain.feedback import CookedStatus, Rating, RecipeFeedback
from idlcooking.domain.planning import RecipeCandidate
from idlcooking.domain.profile import BudgetLevel, UserProfile
from idlcooking.services.recipe_discovery import RecipeDiscoveryService


def _offline_facade() -> TelegramPlanningFacade:
    """A facade whose recipe discovery never touches the network, using seed recipes."""
    return TelegramPlanningFacade(
        "sqlite:///:memory:", recipe_discovery=RecipeDiscoveryService(source_urls=())
    )


def test_bot_language_defaults_to_english() -> None:
    assert resolve_language(None) == "en"
    assert resolve_language("ru") == "en"
    assert "weekly menu" in t("en", "start")


def test_bot_commands_lists_every_expected_command_with_a_description() -> None:
    commands = bot_commands("en")

    assert [name for name, _ in commands] == [
        "start",
        "plan",
        "schedule",
        "profile",
        "feedback",
        "fridge",
        "help",
        "delete_my_data",
    ]
    assert all(description.strip() for _, description in commands)


def test_terminal_text_appends_help_hint_only_when_there_is_no_keyboard() -> None:
    # Issue #20: a terminal response without its own keyboard must still point
    # somewhere, so callers can't silently reintroduce a dead end.
    with_keyboard = _terminal_text("en", "Done.", has_keyboard=True)
    without_keyboard = _terminal_text("en", "Done.", has_keyboard=False)

    assert with_keyboard == "Done."
    assert without_keyboard == "Done.\n\nSend /help to see everything I can do."


def test_plan_keyboard_draft_offers_accept_and_regenerate_but_not_rate() -> None:
    # Issue #23: rating meals that haven't been cooked yet doesn't make sense.
    buttons = [
        button
        for row in plan_keyboard("en", accepted=False).inline_keyboard
        for button in row
    ]
    callback_data = [button.callback_data for button in buttons]

    assert _PLAN_ACCEPT_CALLBACK in callback_data
    assert _PLAN_REGENERATE_CALLBACK in callback_data
    assert _PLAN_RATE_CALLBACK not in callback_data


def test_plan_keyboard_accepted_drops_accept_and_regenerate_but_offers_rate() -> None:
    # Issue #27: once accepted, Accept/Regenerate no longer apply to a settled plan.
    buttons = [
        button
        for row in plan_keyboard("en", accepted=True).inline_keyboard
        for button in row
    ]
    callback_data = [button.callback_data for button in buttons]

    assert _PLAN_ACCEPT_CALLBACK not in callback_data
    assert _PLAN_REGENERATE_CALLBACK not in callback_data
    assert _PLAN_RATE_CALLBACK in callback_data


def test_back_only_keyboard_points_to_the_plan_menu() -> None:
    keyboard = _back_only_keyboard("en")

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == _PLAN_BACK_TO_MENU_CALLBACK


def test_help_message_includes_every_command() -> None:
    commands_text = "\n".join(
        f"/{command} — {description}" for command, description in bot_commands("en")
    )
    text = t("en", "help", commands=commands_text)

    for command, _ in bot_commands("en"):
        assert f"/{command}" in text


def test_resolve_message_language_is_consistent_for_every_handler() -> None:
    message_with_user = SimpleNamespace(from_user=SimpleNamespace(language_code="ru"))
    message_without_user = SimpleNamespace(from_user=None)

    assert _resolve_message_language(message_with_user) == resolve_language("ru")
    assert _resolve_message_language(message_without_user) == resolve_language(None)


def test_telegram_planning_facade_generates_and_persists_plan() -> None:
    facade = _offline_facade()

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=12345, inventory_text="rice"
    )

    assert summary.planning_cycle_id == 1
    # 7 lunches plus a same-day leftover dinner for every day.
    assert len(summary.menu_lines) == 14
    assert any("(dinner)" in line for line in summary.menu_lines)
    assert any("(lunch)" in line for line in summary.menu_lines)
    assert any("already have" in line for line in summary.shopping_lines)


def test_telegram_planning_facade_can_disable_dinner_leftovers() -> None:
    facade = _offline_facade()

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=12345, inventory_text="rice", include_dinner_leftovers=False
    )

    assert len(summary.menu_lines) == 7
    assert all("(dinner)" not in line for line in summary.menu_lines)


def test_telegram_planning_facade_respects_requested_day_count() -> None:
    facade = _offline_facade()

    lunch_only = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_dinner_leftovers=False
    )
    assert len(lunch_only.menu_lines) == 3

    with_dinners = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_dinner_leftovers=True
    )
    # 3 lunches plus a same-day leftover dinner for every day.
    assert len(with_dinners.menu_lines) == 6


def test_telegram_planning_facade_can_include_breakfast() -> None:
    facade = _offline_facade()

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_dinner_leftovers=False, include_breakfast=True
    )

    # 3 lunches plus a breakfast for every day.
    assert len(summary.menu_lines) == 6
    assert any("(breakfast)" in line for line in summary.menu_lines)


def test_telegram_planning_facade_caches_discovered_recipes_and_reuses_them() -> None:
    discovered_recipe = RecipeCandidate(
        title="Discovered Soup",
        source_url="https://example.com/soup",
        ingredients=("lentils", "carrot"),
        active_time_minutes=15,
    )

    def discover_once() -> list[RecipeCandidate]:
        raise AssertionError("discovery should not run again once the cache is populated")

    discovery = RecipeDiscoveryService(source_urls=("https://example.com/soup",))
    discovery.discover = lambda: [discovered_recipe]  # type: ignore[method-assign]
    facade = TelegramPlanningFacade("sqlite:///:memory:", recipe_discovery=discovery)

    first = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_dinner_leftovers=False
    )
    assert any("Discovered Soup" in line for line in first.menu_lines)
    assert [recipe.source_url for recipe in facade.recipe_catalog.get_all_recipes()] == [
        "https://example.com/soup"
    ]

    # Second call must reuse the cache and never hit discovery again.
    discovery.discover = discover_once  # type: ignore[method-assign]
    second = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_dinner_leftovers=False
    )
    assert any("Discovered Soup" in line for line in second.menu_lines)


def test_telegram_planning_facade_falls_back_to_seed_recipes_when_discovery_fails() -> None:
    def failing_discover() -> list[RecipeCandidate]:
        raise RuntimeError("network down")

    discovery = RecipeDiscoveryService(source_urls=("https://example.com/broken",))
    discovery.discover = failing_discover  # type: ignore[method-assign]
    facade = TelegramPlanningFacade("sqlite:///:memory:", recipe_discovery=discovery)

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_dinner_leftovers=False
    )

    assert len(summary.menu_lines) == 7
    assert facade.recipe_catalog.get_all_recipes() == []


def test_telegram_planning_facade_returns_default_profile_summary() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.get_profile_summary(telegram_user_id=12345)

    assert summary.household_size == 1
    assert summary.cooking_effort_minutes == 20
    assert summary.planning_weekday == 5
    assert summary.planning_time == "09:00"


def test_telegram_planning_facade_deletes_user_data() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")
    facade.ensure_user_defaults(telegram_user_id=12345)

    facade.delete_user_data(telegram_user_id=12345)

    assert facade.users.get_user_id_by_telegram_id(12345) is None


def test_telegram_planning_facade_tracks_consent() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    assert facade.has_user_consented(telegram_user_id=12345) is False

    facade.record_consent(telegram_user_id=12345)

    assert facade.has_user_consented(telegram_user_id=12345) is True


def test_telegram_planning_facade_returns_default_schedule_summary() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.get_schedule_summary(telegram_user_id=12345)

    assert summary.weekday == 5
    assert summary.weekday_name == "Saturday"
    assert summary.at_time == "09:00"
    assert summary.timezone == "Europe/Berlin"


def test_telegram_planning_facade_updates_schedule() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.update_schedule(
        telegram_user_id=12345,
        weekday=2,
        at_time=time(18, 30),
        timezone="America/New_York",
    )

    assert summary.weekday == 2
    assert summary.weekday_name == "Wednesday"
    assert summary.at_time == "18:30"
    assert summary.timezone == "America/New_York"
    assert facade.get_schedule_summary(telegram_user_id=12345) == summary


def test_telegram_planning_facade_saves_profile_from_onboarding() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")
    profile = UserProfile(
        household_size=3,
        cooking_effort_minutes=15,
        allergies=("peanut",),
        budget_level=BudgetLevel.LOW,
    )

    facade.save_profile(telegram_user_id=12345, profile=profile)

    summary = facade.get_profile_summary(telegram_user_id=12345)
    assert summary.household_size == 3
    assert summary.cooking_effort_minutes == 15


def test_telegram_planning_facade_has_no_feedback_targets_without_a_plan() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    assert facade.get_latest_cycle_feedback_targets(telegram_user_id=1) is None


def test_telegram_planning_facade_feedback_targets_deduplicate_lunch_leftovers() -> None:
    facade = _offline_facade()
    facade.generate_plan_from_text_inventory(telegram_user_id=1, include_dinner_leftovers=True)

    targets = facade.get_latest_cycle_feedback_targets(telegram_user_id=1)

    assert targets is not None
    planning_cycle_id, items = targets
    assert planning_cycle_id == 1
    source_urls = [item.source_url for item in items]
    assert len(source_urls) == len(set(source_urls))


def test_telegram_planning_facade_feedback_excludes_disliked_recipe_from_next_plan() -> None:
    recipe_a = RecipeCandidate(
        title="Recipe A",
        source_url="https://example.com/a",
        ingredients=("a",),
        active_time_minutes=5,
    )
    recipe_b = RecipeCandidate(
        title="Recipe B",
        source_url="https://example.com/b",
        ingredients=("b",),
        active_time_minutes=20,
    )
    discovery = RecipeDiscoveryService(source_urls=("https://example.com/a",))
    discovery.discover = lambda: [recipe_a, recipe_b]  # type: ignore[method-assign]
    facade = TelegramPlanningFacade("sqlite:///:memory:", recipe_discovery=discovery)

    first = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_dinner_leftovers=False
    )
    assert "Recipe A" in first.menu_lines[0]

    planning_cycle_id, _ = facade.get_latest_cycle_feedback_targets(telegram_user_id=1)
    facade.record_feedback(
        telegram_user_id=1,
        planning_cycle_id=planning_cycle_id,
        feedback=RecipeFeedback(
            recipe_source_url="https://example.com/a",
            recipe_title="Recipe A",
            cooked_status=CookedStatus.COOKED,
            rating=Rating.DISLIKED,
            effort_feedback="too_much_effort",
        ),
    )

    second = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_dinner_leftovers=False
    )
    assert all("Recipe A" not in line for line in second.menu_lines)
    assert "Recipe B" in second.menu_lines[0]


def test_telegram_planning_facade_accept_latest_cycle() -> None:
    facade = _offline_facade()

    assert facade.accept_latest_cycle(telegram_user_id=1) is False

    facade.generate_plan_from_text_inventory(telegram_user_id=1, include_dinner_leftovers=False)

    assert facade.accept_latest_cycle(telegram_user_id=1) is True


def test_telegram_planning_facade_reports_whether_latest_cycle_is_accepted() -> None:
    facade = _offline_facade()

    assert facade.is_latest_cycle_accepted(telegram_user_id=1) is False

    facade.generate_plan_from_text_inventory(telegram_user_id=1, include_dinner_leftovers=False)
    assert facade.is_latest_cycle_accepted(telegram_user_id=1) is False

    facade.accept_latest_cycle(telegram_user_id=1)
    assert facade.is_latest_cycle_accepted(telegram_user_id=1) is True


def test_telegram_planning_facade_shopping_list_lines() -> None:
    facade = _offline_facade()

    assert facade.get_latest_shopping_list_lines(telegram_user_id=1) == ()

    facade.generate_plan_from_text_inventory(
        telegram_user_id=1, inventory_text="rice", include_dinner_leftovers=False
    )

    lines = facade.get_latest_shopping_list_lines(telegram_user_id=1)
    assert lines
    assert any("already have" in line for line in lines)
    # Grouped by category: at least one category header line ending in ":".
    assert any(line.endswith(":") for line in lines)


def test_telegram_planning_facade_returns_recipe_details_grouped_by_day() -> None:
    facade = _offline_facade()

    assert facade.get_latest_recipe_details_by_day(telegram_user_id=1) == []

    facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=2, include_dinner_leftovers=True
    )

    days = facade.get_latest_recipe_details_by_day(telegram_user_id=1)
    assert len(days) == 2
    assert [item.meal_type for item in days[0]] == ["lunch", "dinner"]
    assert [item.meal_type for item in days[1]] == ["lunch", "dinner"]
    assert days[0][0].source_url.startswith("https://")
    assert isinstance(days[0][0].ingredients, tuple)


def test_telegram_planning_facade_rebuilds_plan_summary_without_regenerating() -> None:
    facade = _offline_facade()

    assert facade.get_latest_plan_summary(telegram_user_id=1) is None

    original = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_dinner_leftovers=False
    )

    rebuilt = facade.get_latest_plan_summary(telegram_user_id=1)

    assert rebuilt is not None
    assert rebuilt.planning_cycle_id == original.planning_cycle_id
    assert rebuilt.menu_lines == original.menu_lines
    # Rebuilding must not create a new planning cycle.
    assert facade.cycles.get_latest_cycle_id(facade.users.get_user_id_by_telegram_id(1)) == 1


def test_parse_list_answer_treats_none_and_skip_as_empty() -> None:
    assert _parse_list_answer("none") == ()
    assert _parse_list_answer("Skip") == ()
    assert _parse_list_answer("") == ()
    assert _parse_list_answer("peanut, shellfish;  soy ") == ("peanut", "shellfish", "soy")


def test_telegram_planning_facade_new_schedule_is_not_immediately_due() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")
    facade.ensure_user_defaults(telegram_user_id=1)

    # A freshly created schedule must not fire on the very next scheduler tick;
    # it should wait for its actual next occurrence.
    just_created = datetime.now(UTC)
    assert facade.get_due_telegram_user_ids(just_created) == []

    a_week_and_a_day_later = just_created + timedelta(days=8)
    assert facade.get_due_telegram_user_ids(a_week_and_a_day_later) == [1]

    facade.mark_schedule_triggered(1, a_week_and_a_day_later)
    assert facade.get_due_telegram_user_ids(a_week_and_a_day_later) == []
