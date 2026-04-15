from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationCreateRequest, NotificationResponse


class NotificationService:
    def create(self, db: Session, user: User, payload: NotificationCreateRequest) -> NotificationResponse:
        item = Notification(
            user_id=user.id,
            category=payload.category,
            title=payload.title,
            message=payload.message,
            is_read=False,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return NotificationResponse.model_validate(item)

    def create_internal(self, db: Session, user_id: int, category: str, title: str, message: str) -> None:
        item = Notification(user_id=user_id, category=category, title=title, message=message, is_read=False)
        db.add(item)

    def list_for_user(self, db: Session, user: User) -> list[NotificationResponse]:
        items = list(
            db.scalars(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
            ).all()
        )
        return [NotificationResponse.model_validate(item) for item in items]

    def mark_all_read(self, db: Session, user: User) -> int:
        items = list(db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))).all())
        for item in items:
            item.is_read = True
            db.add(item)
        db.commit()
        return len(items)


notification_service = NotificationService()
