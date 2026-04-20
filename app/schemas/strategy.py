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


class AdminStrategyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    strategy_tag: str = Field(min_length=2, max_length=100)
    exchange: str = Field(default="Delta Exchange", min_length=2, max_length=80)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high)$")
    logo_url: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    followers: int = Field(default=0, ge=0)
    recommended_margin: Decimal = Field(gt=0)
    mdd_percent: Decimal = Field(ge=0)
    win_rate_percent: Decimal = Field(ge=0, le=100)
    pnl: Decimal
    roi_percent: Decimal
    chart_points: list[Decimal] = Field(default_factory=list, max_length=24)
    academy_slugs: list[str] = Field(default_factory=list, max_length=12)
    is_public: bool = True
    is_featured: bool = False


class AdminStrategyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    strategy_tag: str | None = Field(default=None, min_length=2, max_length=100)
    exchange: str | None = Field(default=None, min_length=2, max_length=80)
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high)$")
    logo_url: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)
    followers: int | None = Field(default=None, ge=0)
    recommended_margin: Decimal | None = Field(default=None, gt=0)
    mdd_percent: Decimal | None = Field(default=None, ge=0)
    win_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    pnl: Decimal | None = None
    roi_percent: Decimal | None = None
    chart_points: list[Decimal] | None = Field(default=None, max_length=24)
    academy_slugs: list[str] | None = Field(default=None, max_length=12)
    is_public: bool | None = None
    is_featured: bool | None = None


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
    exchange: str
    risk_level: str
    logo_url: str | None
    image_url: str | None
    tags: str | None
    followers: int
    recommended_margin: Decimal
    mdd_percent: Decimal
    win_rate_percent: Decimal
    pnl: Decimal
    roi_percent: Decimal
    chart_points: str | None
    academy_slugs: str | None
    is_featured: bool
    created_at: datetime
