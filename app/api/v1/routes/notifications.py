from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.notification import NotificationCreateRequest, NotificationResponse
from app.services.notification_service import notification_service


router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
def list_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return notification_service.list_for_user(db, current_user)


@router.post("", response_model=NotificationResponse)
def create_notification(
    payload: NotificationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notification_service.create(db, current_user, payload)


@router.post("/mark-all-read", response_model=MessageResponse)
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = notification_service.mark_all_read(db, current_user)
    return MessageResponse(message=f"Marked {updated} notifications as read")
