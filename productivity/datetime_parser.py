"""Timezone-aware date and time parsing with calendar validation and DST guards."""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Optional


class DateTimeParser:
    """Robust natural language and ISO datetime parser for local scheduling."""

    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    MONTH_NAMES = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }

    @classmethod
    def now_local(cls) -> datetime:
        """Return current local datetime with system timezone offset."""
        return datetime.now().astimezone()

    @classmethod
    def to_iso(cls, dt: datetime) -> str:
        """Format datetime as ISO 8601 string with timezone offset."""
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.isoformat()

    @classmethod
    def from_iso(cls, text: str) -> datetime:
        """Parse ISO string into timezone-aware datetime."""
        dt = datetime.fromisoformat(text.strip())
        if dt.tzinfo is None:
            return dt.astimezone()
        return dt

    @classmethod
    def validate_date(cls, year: int, month: int, day: int) -> None:
        """Validate that a year, month, and day represent a valid calendar date."""
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month: {month}")
        _, max_days = calendar.monthrange(year, month)
        if day < 1 or day > max_days:
            raise ValueError(
                f"Invalid calendar date: {year}-{month:02d}-{day:02d}. "
                f"Month {month} only has {max_days} days."
            )

    @classmethod
    def guard_dst(cls, dt: datetime) -> datetime:
        """Apply DST guards: ensure fold=0 for fall-back overlap, forward-fold for spring-forward gap."""
        # Ensure fold=0 for earliest local occurrence in ambiguous times
        try:
            guarded = dt.replace(fold=0)
        except Exception:
            guarded = dt

        # Test if roundtrip through UTC preserves exact local representation
        # (detects spring-forward gap hour where local time does not exist)
        try:
            utc_dt = guarded.astimezone(timezone.utc)
            local_roundtrip = utc_dt.astimezone(guarded.tzinfo)
            if (
                local_roundtrip.hour != guarded.hour
                or local_roundtrip.minute != guarded.minute
            ):
                # We landed in a spring-forward transition gap.
                # Advance to local_roundtrip (next valid minute).
                return local_roundtrip
        except Exception:
            pass

        return guarded

    @classmethod
    def parse(cls, text: str, reference_dt: Optional[datetime] = None) -> datetime:
        """Parse a relative or absolute date/time string into a timezone-aware datetime."""
        if not text or not text.strip():
            raise ValueError("Empty date/time input.")

        raw = text.strip().lower()
        now = reference_dt if reference_dt is not None else cls.now_local()
        if now.tzinfo is None:
            now = now.astimezone()

        # 1. Direct ISO parse check (e.g. 2026-10-15T15:30:00 or 2026-10-15 15:30)
        iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ t](\d{1,2}):(\d{2})(?::(\d{2}))?)?.*$", raw)
        if iso_match:
            year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            cls.validate_date(year, month, day)
            hour = int(iso_match.group(4)) if iso_match.group(4) else 9
            minute = int(iso_match.group(5)) if iso_match.group(5) else 0
            second = int(iso_match.group(6)) if iso_match.group(6) else 0
            res = datetime(year, month, day, hour, minute, second, tzinfo=now.tzinfo)
            return cls.guard_dst(res)

        # 2. Relative offset: "in X seconds/minutes/hours/days/weeks"
        rel_match = re.search(
            r"in\s+(\d+(?:\.\d+)?)\s*(s(?:ec(?:ond)?)?|m(?:in(?:ute)?)?|h(?:our)?|d(?:ay)?|w(?:eek)?|month|year)s?",
            raw,
        )
        if rel_match:
            amount = float(rel_match.group(1))
            unit = rel_match.group(2)
            if unit.startswith("s"):
                delta = timedelta(seconds=amount)
            elif unit.startswith("m") and "month" not in unit:
                delta = timedelta(minutes=amount)
            elif unit.startswith("h"):
                delta = timedelta(hours=amount)
            elif unit.startswith("d"):
                delta = timedelta(days=amount)
            elif unit.startswith("w"):
                delta = timedelta(weeks=amount)
            elif unit.startswith("month"):
                delta = timedelta(days=amount * 30.5)
            elif unit.startswith("year"):
                delta = timedelta(days=amount * 365)
            else:
                delta = timedelta(minutes=amount)
            return cls.guard_dst(now + delta)

        # 3. "tomorrow" with optional time
        if "tomorrow" in raw:
            base_date = now.date() + timedelta(days=1)
            parsed_time = cls._extract_time(raw)
            hour = parsed_time[0] if parsed_time else 9
            minute = parsed_time[1] if parsed_time else 0
            res = datetime(base_date.year, base_date.month, base_date.day, hour, minute, 0, tzinfo=now.tzinfo)
            return cls.guard_dst(res)

        # 4. "today" with explicit time
        if "today" in raw:
            parsed_time = cls._extract_time(raw)
            if not parsed_time:
                raise ValueError("When specifying 'today', a specific time must be provided (e.g., 'today at 4pm').")
            hour, minute = parsed_time
            res = datetime(now.year, now.month, now.day, hour, minute, 0, tzinfo=now.tzinfo)
            return cls.guard_dst(res)

        # 5. Day of week: "monday", "next friday at 3pm", "on tuesday 10:00"
        for day_name, day_idx in cls.WEEKDAYS.items():
            if re.search(rf"\b(?:next\s+|on\s+)?{day_name}\b", raw):
                days_ahead = (day_idx - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                if "next " in raw and days_ahead < 7:
                    days_ahead += 7
                target_date = now.date() + timedelta(days=days_ahead)
                parsed_time = cls._extract_time(raw)
                hour = parsed_time[0] if parsed_time else 9
                minute = parsed_time[1] if parsed_time else 0
                res = datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0, tzinfo=now.tzinfo)
                return cls.guard_dst(res)

        # 6. Natural month date: "October 15", "15th October at 4pm", "Oct 15 2026 3pm"
        for m_name, m_num in cls.MONTH_NAMES.items():
            m_match = re.search(rf"\b{m_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?", raw)
            if not m_match:
                m_match = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{m_name}(?:\s*,?\s*(\d{{4}}))?", raw)
            if m_match:
                day = int(m_match.group(1))
                year = int(m_match.group(2)) if m_match.group(2) else now.year
                cls.validate_date(year, m_num, day)
                parsed_time = cls._extract_time(raw)
                hour = parsed_time[0] if parsed_time else 9
                minute = parsed_time[1] if parsed_time else 0
                res = datetime(year, m_num, day, hour, minute, 0, tzinfo=now.tzinfo)
                # If year was implicit and resulting date is in the past, roll to next year
                if not m_match.group(2) and res < now:
                    res = res.replace(year=year + 1)
                return cls.guard_dst(res)

        # 7. Time of day alone: "at 5pm", "5:30 pm", "17:00", "at 9am"
        parsed_time = cls._extract_time(raw)
        if parsed_time:
            hour, minute = parsed_time
            candidate = datetime(now.year, now.month, now.day, hour, minute, 0, tzinfo=now.tzinfo)
            if candidate <= now:
                # Time already passed today, assume tomorrow
                candidate = candidate + timedelta(days=1)
            return cls.guard_dst(candidate)

        raise ValueError(f"Could not parse date/time from expression: '{text}'")

    @classmethod
    def _extract_time(cls, text: str) -> Optional[tuple[int, int]]:
        """Extract hour and minute from text like '5pm', '5:30 am', 'at 17:00', '14:30'."""
        # Match 12-hour: 'at 5pm', '5:30 pm', '5 pm', '5:15am'
        m12 = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
        if m12:
            hour = int(m12.group(1))
            minute = int(m12.group(2)) if m12.group(2) else 0
            meridiem = m12.group(3)
            if hour < 1 or hour > 12 or minute < 0 or minute > 59:
                return None
            if meridiem == "pm" and hour != 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            return hour, minute

        # Match 24-hour: 'at 17:30', '14:00', '09:15'
        m24 = re.search(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", text)
        if m24:
            return int(m24.group(1)), int(m24.group(2))

        return None
