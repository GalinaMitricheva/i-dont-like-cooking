import asyncio
from datetime import UTC, datetime, timedelta

from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.scheduler import run_due_planning_cycles, send_due_feedback_requests
from idlcooking.services.recipe_discovery import RecipeDiscoveryService


class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent_messages.append((chat_id, text))


class _FailingBot:
    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        raise RuntimeError("Telegram is unreachable")


def _offline_facade() -> TelegramPlanningFacade:
    return TelegramPlanningFacade(
        "sqlite:///:memory:", recipe_discovery=RecipeDiscoveryService(source_urls=())
    )


def test_run_due_planning_cycles_sends_plan_and_marks_triggered() -> None:
    facade = _offline_facade()
    facade.ensure_user_defaults(telegram_user_id=1)
    # Force "due" regardless of what day it actually is when the test runs.
    facade.schedules.mark_schedule_triggered(1, None)
    bot = _FakeBot()

    asyncio.run(run_due_planning_cycles(bot, facade))

    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0][0] == 1

    # Running again immediately must not double-send.
    asyncio.run(run_due_planning_cycles(bot, facade))
    assert len(bot.sent_messages) == 1


def test_run_due_planning_cycles_retries_after_a_send_failure() -> None:
    facade = _offline_facade()
    facade.ensure_user_defaults(telegram_user_id=1)
    facade.schedules.mark_schedule_triggered(1, None)

    asyncio.run(run_due_planning_cycles(_FailingBot(), facade))

    # The failed send must not be marked as triggered, so it stays due for a retry.
    bot = _FakeBot()
    asyncio.run(run_due_planning_cycles(bot, facade))
    assert len(bot.sent_messages) == 1


# Midday UTC -> Europe/Berlin 13:00–14:00, inside the 07:00–20:00 send window.
_ACCEPTED = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
_SEND_NOW = _ACCEPTED + timedelta(days=10)  # plan period is well over by now


def _accept_at(facade: TelegramPlanningFacade, accepted_at: datetime) -> int:
    """Accept the user's latest plan, pinning accepted_at to a fixed instant."""
    facade.accept_latest_cycle(telegram_user_id=1)
    user_id = facade.users.get_user_id_by_telegram_id(1)
    cycle_id = facade.cycles.get_latest_cycle_id(user_id)
    facade.connection.execute(
        "UPDATE planning_cycles SET accepted_at = ? WHERE id = ?",
        (accepted_at.strftime("%Y-%m-%d %H:%M:%S"), cycle_id),
    )
    facade.connection.commit()
    return cycle_id


def test_send_due_feedback_requests_sends_once_and_does_not_repeat() -> None:
    facade = _offline_facade()
    facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=2, include_dinner_leftovers=False
    )
    _accept_at(facade, _ACCEPTED)
    bot = _FakeBot()

    asyncio.run(send_due_feedback_requests(bot, facade, now=_SEND_NOW))
    assert len(bot.sent_messages) == 1
    assert bot.sent_messages[0][0] == 1

    # A second tick must not re-send the same request.
    asyncio.run(send_due_feedback_requests(bot, facade, now=_SEND_NOW))
    assert len(bot.sent_messages) == 1


def test_send_due_feedback_requests_retries_after_a_send_failure() -> None:
    facade = _offline_facade()
    facade.generate_plan_from_text_inventory(
        telegram_user_id=1, days=2, include_dinner_leftovers=False
    )
    _accept_at(facade, _ACCEPTED)

    # A failed send must not be marked requested, so it stays due for a retry.
    asyncio.run(send_due_feedback_requests(_FailingBot(), facade, now=_SEND_NOW))

    bot = _FakeBot()
    asyncio.run(send_due_feedback_requests(bot, facade, now=_SEND_NOW))
    assert len(bot.sent_messages) == 1
