import asyncio

from idlcooking.bot.planning import TelegramPlanningFacade
from idlcooking.scheduler import run_due_planning_cycles
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
