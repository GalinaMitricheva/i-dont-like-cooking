from datetime import datetime, time
from zoneinfo import ZoneInfo

from idlcooking.domain.schedule import PlanningSchedule


def test_next_run_uses_future_default_saturday() -> None:
    schedule = PlanningSchedule(weekday=5, at_time=time(9), timezone="Europe/Berlin")
    now = datetime(2026, 7, 4, 8, 30, tzinfo=ZoneInfo("Europe/Berlin"))

    assert schedule.next_run_after(now) == datetime(
        2026, 7, 4, 9, 0, tzinfo=ZoneInfo("Europe/Berlin")
    )


def test_next_run_rolls_to_next_week_after_planning_time() -> None:
    schedule = PlanningSchedule(weekday=5, at_time=time(9), timezone="Europe/Berlin")
    now = datetime(2026, 7, 4, 9, 1, tzinfo=ZoneInfo("Europe/Berlin"))

    assert schedule.next_run_after(now) == datetime(
        2026, 7, 11, 9, 0, tzinfo=ZoneInfo("Europe/Berlin")
    )
