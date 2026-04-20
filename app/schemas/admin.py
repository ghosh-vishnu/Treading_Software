from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AdminDashboardMetrics(BaseModel):
    total_users: int
    active_traders: int
    total_strategies: int
    trades_today: int
    revenue: Decimal
    profit_share: Decimal
    total_followers: int
    total_subscriptions: int


class ChartPoint(BaseModel):
    label: str
    value: Decimal


class ActivityItem(BaseModel):
    id: str
    category: str
    title: str
    detail: str
    created_at: datetime


class PagedMeta(BaseModel):
    page: int
    page_size: int
    total: int


class AdminUserItem(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    kyc_status: str
    subscription_status: str
    linked_exchange_accounts: int
    followers: int
    wallet_balance: Decimal
    created_at: datetime


class AdminUserListResponse(BaseModel):
    meta: PagedMeta
    items: list[AdminUserItem]


class AdminUserBanRequest(BaseModel):
    is_active: bool


class AdminTradeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    order_type: str
    status: str
    pnl: Decimal
    broker: str
    strategy_tag: str | None
    created_at: datetime


class AdminTradeListResponse(BaseModel):
    meta: PagedMeta
    items: list[AdminTradeItem]


class ManualCloseTradeRequest(BaseModel):
    close_price: Decimal = Field(gt=0)


class StrategyBulkActionRequest(BaseModel):
    strategy_ids: list[int] = Field(min_length=1, max_length=100)
    action: str = Field(pattern="^(publish|unpublish|feature|unfeature|delete|duplicate)$")


class StrategyPerformanceResponse(BaseModel):
    equity_curve: list[ChartPoint]
    daily_returns: list[ChartPoint]
    monthly_returns: list[ChartPoint]
    drawdown_curve: list[ChartPoint]
    win_loss_ratio: Decimal
    average_rr: Decimal
    open_positions: int


class BroadcastNotificationRequest(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=5, max_length=2000)
    category: str = Field(default="admin", max_length=40)


class PlatformSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_name: str
    support_email: str
    fee_percent: float
    profit_share_percent: float
    maintenance_mode: bool
    telegram_alerts_enabled: bool
    telegram_chat_id: str | None
    exchange_api_key: str | None
    exchange_api_secret: str | None
    updated_at: datetime


class PlatformSettingsUpdateRequest(BaseModel):
    site_name: str = Field(min_length=3, max_length=120)
    support_email: str = Field(min_length=5, max_length=255)
    fee_percent: float = Field(ge=0, le=100)
    profit_share_percent: float = Field(ge=0, le=100)
    maintenance_mode: bool = False
    telegram_alerts_enabled: bool = False
    telegram_chat_id: str | None = Field(default=None, max_length=128)
    exchange_api_key: str | None = Field(default=None, max_length=255)
    exchange_api_secret: str | None = Field(default=None, max_length=255)


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    action: str
    target_type: str
    target_id: str | None
    severity: str
    metadata_json: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    meta: PagedMeta
    items: list[AuditLogResponse]
