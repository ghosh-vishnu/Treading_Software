from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrokerConnectRequest(BaseModel):
    broker_name: str = Field(pattern="^(delta|zerodha|binance)$")
    api_key: str = Field(min_length=8, max_length=255)
    api_secret: str = Field(min_length=8, max_length=255)
    passphrase: str | None = Field(default=None, max_length=255)


class BrokerAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    broker_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: str | None


class BrokerBalanceResponse(BaseModel):
    broker: str
    balance: Decimal
    currency: str
    available_balance: Decimal | None = None


class BrokerPositionResponse(BaseModel):
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    unrealized_pnl: Decimal


class BrokerOrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    broker: str = Field(default="delta", pattern="^(delta|zerodha|binance)$")


class BrokerOrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal | None
    order_type: str
    status: str
    raw: dict[str, Any]