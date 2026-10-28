"""Recurrence calculations, month-end clamping, and missed backlog collapsing."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Optional

from productivity.models import RecurrenceType


class RecurrenceEngine:
    """Calculates next occurrences for recurring reminders and collapses backlogs."""

    @classmethod
    def calculate_next_occurrence(
        cls, current_dt: datetime, recurrence: str | RecurrenceType
    ) -> Optional[datetime]:
        """Calculate the subsequent occurrence timestamp from a current timestamp."""
        rec_type = recurrence.value if isinstance(recurrence, RecurrenceType) else str(recurrence).lower()

        if rec_type == RecurrenceType.NONE.value or not rec_type:
            return None

        if rec_type == RecurrenceType.DAILY.value:
            return current_dt + timedelta(days=1)

        elif rec_type == RecurrenceType.WEEKDAYS.value:
            next_dt = current_dt + timedelta(days=1)
            while next_dt.weekday() in (5, 6):  # 5=Saturday, 6=Sunday
                next_dt += timedelta(days=1)
            return next_dt

        elif rec_type == RecurrenceType.WEEKLY.value:
            return current_dt + timedelta(weeks=1)

        elif rec_type == RecurrenceType.MONTHLY.value:
            # Advance month by 1
            year = current_dt.year
            month = current_dt.month + 1
            if month > 12:
                month = 1
                year += 1

            # Clamp day to max days in target month
            _, max_days = calendar.monthrange(year, month)
            target_day = min(current_dt.day, max_days)

            return current_dt.replace(
                year=year,
                month=month,
                day=target_day,
            )

        raise ValueError(f"Unsupported recurrence rule: '{recurrence}'")

    @classmethod
    def collapse_missed_recurrences(
        cls, last_remind_dt: datetime, recurrence: str | RecurrenceType, now_dt: datetime
    ) -> tuple[Optional[datetime], int]:
        """Advance past all elapsed occurrences while system was offline.

        Returns:
            tuple[Optional[datetime], int]: (next_future_occurrence, count_of_missed_occurrences)
        """
        rec_type = recurrence.value if isinstance(recurrence, RecurrenceType) else str(recurrence).lower()
        if rec_type == RecurrenceType.NONE.value:
            return None, 1 if last_remind_dt <= now_dt else 0

        missed_count = 0
        cur_dt = last_remind_dt

        # Count the first occurrence if it already passed
        if cur_dt <= now_dt:
            missed_count += 1

        # Advance until we find a timestamp strictly in the future
        max_loop = 1000
        while cur_dt <= now_dt and max_loop > 0:
            max_loop -= 1
            next_candidate = cls.calculate_next_occurrence(cur_dt, rec_type)
            if not next_candidate:
                break
            cur_dt = next_candidate
            if cur_dt <= now_dt:
                missed_count += 1

        return cur_dt if cur_dt > now_dt else None, missed_count
