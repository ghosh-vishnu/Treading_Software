from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrategySignalRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: str = Field(pattern="^(BUY|SELL)$")
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_tag: str = Field(min_length=2, max_length=100)
    broker: str = Field(default="delta", pattern="^(delta|zerodha|binance)$")
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    strategy_tag: str = Field(min_length=2, max_length=100)
    is_public: bool = False


class StrategySignalResponse(BaseModel):
    accepted: bool
    message: str


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    user_id: int
    strategy_tag: str
    is_public: bool
    created_at: datetime
