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


def test_latest_occurrence_is_today_when_scheduled_time_has_passed() -> None:
    schedule = PlanningSchedule(weekday=5, at_time=time(9), timezone="Europe/Berlin")
    now = datetime(2026, 7, 4, 9, 30, tzinfo=ZoneInfo("Europe/Berlin"))

    assert schedule.latest_occurrence_before_or_at(now) == datetime(
        2026, 7, 4, 9, 0, tzinfo=ZoneInfo("Europe/Berlin")
    )


def test_latest_occurrence_is_at_the_exact_moment() -> None:
    schedule = PlanningSchedule(weekday=5, at_time=time(9), timezone="Europe/Berlin")
    now = datetime(2026, 7, 4, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    assert schedule.latest_occurrence_before_or_at(now) == now


def test_latest_occurrence_rolls_back_to_previous_week_before_scheduled_time() -> None:
    schedule = PlanningSchedule(weekday=5, at_time=time(9), timezone="Europe/Berlin")
    now = datetime(2026, 7, 4, 8, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    assert schedule.latest_occurrence_before_or_at(now) == datetime(
        2026, 6, 27, 9, 0, tzinfo=ZoneInfo("Europe/Berlin")
    )


def test_parse_weekday_accepts_case_insensitive_names() -> None:
    assert parse_weekday("Saturday") == 5
    assert parse_weekday("monday") == 0
    assert weekday_name(5) == "Saturday"


def test_parse_weekday_rejects_unknown_names() -> None:
    with pytest.raises(ValueError):
        parse_weekday("someday")


def test_parse_weekday_accepts_numeric_index_monday_zero() -> None:
    # Issue #34: users try "/schedule 5 ...". Numeric follows Monday=0..Sunday=6.
    assert parse_weekday("0") == 0
    assert parse_weekday("5") == 5
    assert parse_weekday("6") == 6


def test_parse_weekday_rejects_out_of_range_numbers() -> None:
    with pytest.raises(ValueError):
        parse_weekday("7")
