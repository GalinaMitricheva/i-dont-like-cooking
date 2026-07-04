from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.bot.i18n import resolve_language, t


def test_bot_language_defaults_to_english() -> None:
    assert resolve_language(None) == "en"
    assert resolve_language("ru") == "en"
    assert "weekly menu" in t("en", "start")


def test_telegram_planning_facade_generates_and_persists_plan() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.generate_plan_from_text_inventory(telegram_user_id=12345, inventory_text="rice")

    assert summary.planning_cycle_id == 1
    assert len(summary.menu_lines) == 7
    assert any("already have" in line for line in summary.shopping_lines)


def test_telegram_planning_facade_returns_default_profile_summary() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.get_profile_summary(telegram_user_id=12345)

    assert summary.household_size == 1
    assert summary.cooking_effort_minutes == 20
    assert summary.planning_weekday == 5
    assert summary.planning_time == "09:00"
