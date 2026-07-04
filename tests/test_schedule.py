from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from idlcooking.domain.schedule import PlanningSchedule, parse_weekday, weekday_name


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


def test_parse_weekday_accepts_case_insensitive_names() -> None:
    assert parse_weekday("Saturday") == 5
    assert parse_weekday("monday") == 0
    assert weekday_name(5) == "Saturday"


def test_parse_weekday_rejects_unknown_names() -> None:
    with pytest.raises(ValueError):
        parse_weekday("someday")
