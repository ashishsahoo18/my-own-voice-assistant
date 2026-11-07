"""Welcome and startup greeting routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.dependencies import get_current_user
from backend.app.models.user import User
from backend.app.schemas.common import WelcomeResponse

router = APIRouter(prefix="/api/welcome", tags=["Welcome"])


class WelcomeRequest(BaseModel):
    device_name: Optional[str] = "Windows Laptop"


@router.post("", response_model=WelcomeResponse)
def welcome_user(
    body: WelcomeRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate greeting, profile context, and device quick-tips upon app launch or wakeup."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    name = current_user.full_name or "Ashish"

    return WelcomeResponse(
        greeting=f"Welcome back, {name}! OLIVER is online and ready.",
        user_name=name,
        device_name=body.device_name,
        server_time=now_str,
        quick_tips=[
            "Type or speak any programming question or system command.",
            "Use natural voice to search YouTube, browse websites, or take notes.",
            "Say 'Open YouTube' or 'Play <song>' for direct media playback.",
        ],
    )

