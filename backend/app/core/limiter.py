"""Rate limiting module using slowapi."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter keyed by client remote address
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

