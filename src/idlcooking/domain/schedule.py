from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAY_NAMES: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def weekday_name(weekday: int) -> str:
    return WEEKDAY_NAMES[weekday].capitalize()


def parse_weekday(value: str) -> int:
    normalized = value.strip().lower()
    if normalized not in WEEKDAY_NAMES:
        raise ValueError(f"Unknown weekday: {value!r}")
    return WEEKDAY_NAMES.index(normalized)


@dataclass(frozen=True)
class PlanningSchedule:
    """Weekly planning schedule. Weekday follows Python: Monday=0, Sunday=6."""

    weekday: int = 5
    at_time: time = time(hour=9)
    timezone: str = "Europe/Berlin"
    enabled: bool = True

    def next_run_after(self, moment: datetime) -> datetime | None:
        if not self.enabled:
            return None

        zone = ZoneInfo(self.timezone)
        local_moment = moment.astimezone(zone) if moment.tzinfo else moment.replace(tzinfo=zone)
        days_ahead = (self.weekday - local_moment.weekday()) % 7
        candidate_date = local_moment.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, self.at_time, zone)

        if candidate <= local_moment:
            candidate += timedelta(days=7)

        return candidate

    def latest_occurrence_before_or_at(self, moment: datetime) -> datetime:
        """The most recent scheduled occurrence at or before `moment`.

        Used to detect whether a given moment already had its planning cycle
        triggered, independent of how often the scheduler polls.
        """
        zone = ZoneInfo(self.timezone)
        local_moment = moment.astimezone(zone) if moment.tzinfo else moment.replace(tzinfo=zone)
        days_since = (local_moment.weekday() - self.weekday) % 7
        candidate_date = local_moment.date() - timedelta(days=days_since)
        candidate = datetime.combine(candidate_date, self.at_time, zone)

        if candidate > local_moment:
            candidate -= timedelta(days=7)

        return candidate
