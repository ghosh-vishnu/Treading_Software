from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    theme: str
    accent_color: str
    notify_trade_alerts: bool
    notify_strategy_alerts: bool
    notify_system_alerts: bool
    default_lot_size: Decimal
    max_open_positions: int
    created_at: datetime
    updated_at: datetime


class UserSettingsUpdateRequest(BaseModel):
    theme: str = Field(default="dark", pattern="^(dark|light)$")
    accent_color: str = Field(default="lime", max_length=20)
    notify_trade_alerts: bool = True
    notify_strategy_alerts: bool = True
    notify_system_alerts: bool = True
    default_lot_size: Decimal = Field(default=Decimal("1"), gt=0)
    max_open_positions: int = Field(default=5, ge=1, le=100)
