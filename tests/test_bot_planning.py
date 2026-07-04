from datetime import time
from types import SimpleNamespace

from idlcooking.bot.handlers import _resolve_message_language
from idlcooking.bot.i18n import resolve_language, t
from idlcooking.bot.planning import TelegramPlanningFacade


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
