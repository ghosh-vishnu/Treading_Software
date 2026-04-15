from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.settings import UserSettingsResponse, UserSettingsUpdateRequest
from app.services.settings_service import settings_service


class RiskSettingsRequest(BaseModel):
    max_daily_loss: float = Field(gt=0)
    max_trades_per_day: int = Field(ge=1, le=1000)


router = APIRouter()


@router.get("", response_model=UserSettingsResponse)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return settings_service.get_settings(db, current_user)


@router.patch("", response_model=UserSettingsResponse)
def update_settings(
    payload: UserSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return settings_service.update_settings(db, current_user, payload)


@router.patch("/risk", response_model=MessageResponse)
def update_risk_settings(
    payload: RiskSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings_service.update_risk_limits(db, current_user, payload.max_daily_loss, payload.max_trades_per_day)
    return MessageResponse(message="Risk settings updated")
