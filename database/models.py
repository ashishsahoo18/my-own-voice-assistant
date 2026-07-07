from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class UserProfile:
    id: Optional[int] = None
    name: Optional[str] = None
    nickname: Optional[str] = None
    preferred_language: Optional[str] = None
    theme: Optional[str] = None
    voice_settings: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    time_zone: Optional[str] = None
    birthday: Optional[str] = None
    profession: Optional[str] = None
    skills: Optional[str] = None
    interests: Optional[str] = None


@dataclass
class MemoryItem:
    id: Optional[int] = None
    category: Optional[str] = None
    content: Optional[str] = None
    importance: float = 0.5


@dataclass
class Reminder:
    id: Optional[int] = None
    message: Optional[str] = None
    remind_at: Optional[str] = None
    is_done: int = 0
