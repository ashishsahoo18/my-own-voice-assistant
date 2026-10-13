"""Data models for OLIVER 2.0 Browser Automation (Phase 8 Capability 4)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BrowserPageContent:
    """Structured readable content extracted from a webpage."""

    url: str
    requested_url: str
    title: str
    text: str
    meta_description: str = ""
    extracted_length: int = 0
    is_truncated: bool = False
    content_type: str = "text/html"
    status_code: int = 200
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "requested_url": self.requested_url,
            "title": self.title,
            "text": self.text,
            "meta_description": self.meta_description,
            "extracted_length": self.extracted_length,
            "is_truncated": self.is_truncated,
            "content_type": self.content_type,
            "status_code": self.status_code,
            "timestamp": self.timestamp,
        }


@dataclass
class BrowserNavigationResult:
    """Result of navigating to and extracting a webpage."""

    status: str  # VERIFIED, UNVERIFIED, FAILED, DENIED, CANCELLED, TIMEOUT
    url: str
    title: str = ""
    message: str = ""
    page: Optional[BrowserPageContent] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status in {"VERIFIED", "SUCCESS"}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "message": self.message,
            "page": self.page.to_dict() if self.page else None,
            "error": self.error,
        }


@dataclass
class BrowserSummaryResult:
    """Structured summary generated from an approved webpage."""

    status: str
    url: str
    title: str
    summary: str
    key_findings: list[str] = field(default_factory=list)
    source_url: str = ""
    is_grounded: bool = True
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "key_findings": self.key_findings,
            "source_url": self.source_url,
            "is_grounded": self.is_grounded,
            "message": self.message,
        }


@dataclass
class BrowserAnswerResult:
    """Evidence-grounded question answering result based on webpage text."""

    status: str
    question: str
    answer: str
    source_url: str
    has_evidence: bool = True
    citations: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "question": self.question,
            "answer": self.answer,
            "source_url": self.source_url,
            "has_evidence": self.has_evidence,
            "citations": self.citations,
            "message": self.message,
        }
