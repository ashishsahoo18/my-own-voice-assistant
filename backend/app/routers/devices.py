"""Device registration and management routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.device import Device
from backend.app.models.user import User
from backend.app.schemas.device import DeviceRegisterRequest, DeviceResponse

router = APIRouter(prefix="/api/devices", tags=["Devices"])


@router.post("/register", response_model=DeviceResponse)
def register_device(
    body: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register or update a user device (desktop laptop, phone, etc.)."""
    # Check if a device with same name and platform exists for this user
    existing = db.execute(
        select(Device).where(
            Device.user_id == current_user.id,
            Device.device_name == body.device_name,
            Device.platform == body.platform,
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.client_version = body.client_version
        existing.device_type = body.device_type
        existing.last_active_at = now
        db.commit()
        db.refresh(existing)
        device = existing
    else:
        device = Device(
            user_id=current_user.id,
            device_name=body.device_name,
            device_type=body.device_type,
            platform=body.platform,
            client_version=body.client_version,
            registered_at=now,
            last_active_at=now,
        )
        db.add(device)
        db.commit()
        db.refresh(device)

    return DeviceResponse(
        id=device.id,
        device_name=device.device_name,
        device_type=device.device_type,
        platform=device.platform,
        client_version=device.client_version,
        registered_at=device.registered_at,
        last_active_at=device.last_active_at,
    )


@router.get("", response_model=List[DeviceResponse])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all registered devices belonging to the authenticated user."""
    devices = db.execute(
        select(Device)
        .where(Device.user_id == current_user.id)
        .order_by(Device.last_active_at.desc())
    ).scalars().all()

    return [
        DeviceResponse(
            id=d.id,
            device_name=d.device_name,
            device_type=d.device_type,
            platform=d.platform,
            client_version=d.client_version,
            registered_at=d.registered_at,
            last_active_at=d.last_active_at,
        )
        for d in devices
    ]

