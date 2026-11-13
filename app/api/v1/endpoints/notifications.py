from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.system import Notification
from app.schemas.transaction import NotificationOut
from app.schemas.common import ResponseModel, MessageResponse

router = APIRouter()


@router.get("", response_model=ResponseModel[List[NotificationOut]])
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    items = list(result.scalars().all())
    return ResponseModel(data=[NotificationOut.model_validate(n) for n in items])


@router.patch("/{notification_id}/read", response_model=MessageResponse)
async def mark_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == current_user.id
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        await db.commit()
    return MessageResponse(message="Marked as read")


@router.patch("/read-all", response_model=MessageResponse)
async def mark_all_read(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return MessageResponse(message="All notifications marked as read")