from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.settings import UserSettingsResponse, UserSettingsUpdateRequest


class SettingsService:
    def _get_or_create(self, db: Session, user: User) -> UserSettings:
        settings = db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
        if settings:
            return settings

        settings = UserSettings(user_id=user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings

    def get_settings(self, db: Session, user: User) -> UserSettingsResponse:
        settings = self._get_or_create(db, user)
        return UserSettingsResponse.model_validate(settings)

    def update_settings(self, db: Session, user: User, payload: UserSettingsUpdateRequest) -> UserSettingsResponse:
        settings = self._get_or_create(db, user)
        settings.theme = payload.theme
        settings.accent_color = payload.accent_color
        settings.notify_trade_alerts = payload.notify_trade_alerts
        settings.notify_strategy_alerts = payload.notify_strategy_alerts
        settings.notify_system_alerts = payload.notify_system_alerts
        settings.default_lot_size = payload.default_lot_size
        settings.max_open_positions = payload.max_open_positions

        db.add(settings)
        db.commit()
        db.refresh(settings)
        return UserSettingsResponse.model_validate(settings)

    def update_risk_limits(self, db: Session, user: User, max_daily_loss: float, max_trades_per_day: int) -> None:
        if max_trades_per_day < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_trades_per_day must be >= 1")
        user.max_daily_loss = max_daily_loss
        user.max_trades_per_day = max_trades_per_day
        db.add(user)
        db.commit()


settings_service = SettingsService()
