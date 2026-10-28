"""OLIVER 2.0 Browser Automation Package (Phase 8 Capability 4)."""

from browser.driver import IsolatedBrowserManager
from browser.models import (
    BrowserAnswerResult,
    BrowserNavigationResult,
    BrowserPageContent,
    BrowserSummaryResult,
)
from browser.security import (
    BrowserSecurity,
    BrowserSecurityError,
    BrowserSideEffectBlockedError,
    DomainNotAllowedError,
)
from browser.service import BrowserService

__all__ = [
    "BrowserService",
    "IsolatedBrowserManager",
    "BrowserSecurity",
    "BrowserSecurityError",
    "DomainNotAllowedError",
    "BrowserSideEffectBlockedError",
    "BrowserPageContent",
    "BrowserNavigationResult",
    "BrowserSummaryResult",
    "BrowserAnswerResult",
]
