"""API Routers export."""

from backend.app.routers.auth import router as auth_router
from backend.app.routers.chat import router as chat_router
from backend.app.routers.devices import router as devices_router
from backend.app.routers.health import router as health_router
from backend.app.routers.user import router as user_router
from backend.app.routers.welcome import router as welcome_router

__all__ = [
    "auth_router",
    "chat_router",
    "devices_router",
    "health_router",
    "user_router",
    "welcome_router",
]

