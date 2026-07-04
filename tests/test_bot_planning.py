from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

from idlcooking.bot.handlers import _parse_list_answer, _resolve_message_language
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
    # 7 dinners plus a leftover lunch for every day after the first.
    assert len(summary.menu_lines) == 13
    assert any("(dinner)" in line for line in summary.menu_lines)
    assert any("(lunch)" in line for line in summary.menu_lines)
    assert any("already have" in line for line in summary.shopping_lines)


def test_telegram_planning_facade_can_disable_lunch_leftovers() -> None:
    facade = _offline_facade()

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=12345, inventory_text="rice", include_lunch_leftovers=False
    )

    assert len(summary.menu_lines) == 7
    assert all("(lunch)" not in line for line in summary.menu_lines)


def test_telegram_planning_facade_respects_requested_day_count() -> None:
    facade = _offline_facade()

    dinner_only = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_lunch_leftovers=False
    )
    assert len(dinner_only.menu_lines) == 3

    with_lunches = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_lunch_leftovers=True
    )
    # 3 dinners plus a leftover lunch for every day after the first.
    assert len(with_lunches.menu_lines) == 5


def test_telegram_planning_facade_can_include_breakfast() -> None:
    facade = _offline_facade()

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=3, include_lunch_leftovers=False, include_breakfast=True
    )

    # 3 dinners plus a breakfast for every day.
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
        telegram_user_id=1, include_lunch_leftovers=False
    )
    assert any("Discovered Soup" in line for line in first.menu_lines)
    assert [recipe.source_url for recipe in facade.recipe_catalog.get_all_recipes()] == [
        "https://example.com/soup"
    ]

    # Second call must reuse the cache and never hit discovery again.
    discovery.discover = discover_once  # type: ignore[method-assign]
    second = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_lunch_leftovers=False
    )
    assert any("Discovered Soup" in line for line in second.menu_lines)


def test_telegram_planning_facade_falls_back_to_seed_recipes_when_discovery_fails() -> None:
    def failing_discover() -> list[RecipeCandidate]:
        raise RuntimeError("network down")

    discovery = RecipeDiscoveryService(source_urls=("https://example.com/broken",))
    discovery.discover = failing_discover  # type: ignore[method-assign]
    facade = TelegramPlanningFacade("sqlite:///:memory:", recipe_discovery=discovery)

    summary = facade.generate_plan_from_text_inventory(
        telegram_user_id=1, include_lunch_leftovers=False
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
    facade.generate_plan_from_text_inventory(telegram_user_id=1, include_lunch_leftovers=True)

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
        telegram_user_id=1, include_lunch_leftovers=False
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
        telegram_user_id=1, include_lunch_leftovers=False
    )
    assert all("Recipe A" not in line for line in second.menu_lines)
    assert "Recipe B" in second.menu_lines[0]


def test_telegram_planning_facade_accept_latest_cycle() -> None:
    facade = _offline_facade()

    assert facade.accept_latest_cycle(telegram_user_id=1) is False

    facade.generate_plan_from_text_inventory(telegram_user_id=1, include_lunch_leftovers=False)

    assert facade.accept_latest_cycle(telegram_user_id=1) is True


def test_telegram_planning_facade_shopping_list_lines_and_mark_bought() -> None:
    facade = _offline_facade()

    assert facade.get_latest_shopping_list_lines(telegram_user_id=1) == ()
    assert facade.mark_latest_shopping_list_bought(telegram_user_id=1) is False

    facade.generate_plan_from_text_inventory(
        telegram_user_id=1, inventory_text="rice", include_lunch_leftovers=False
    )

    lines = facade.get_latest_shopping_list_lines(telegram_user_id=1)
    assert lines
    assert any("already have" in line for line in lines)
    # Grouped by category: at least one category header line ending in ":".
    assert any(line.endswith(":") for line in lines)
    assert facade.mark_latest_shopping_list_bought(telegram_user_id=1) is True


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
