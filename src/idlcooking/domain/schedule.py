from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


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
