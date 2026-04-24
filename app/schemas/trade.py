from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TradeCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    broker: Literal["delta", "zerodha", "binance"] = "delta"
    strategy_tag: Optional[str] = Field(default=None, max_length=100)
    stop_loss: Optional[Decimal] = Field(default=None, gt=0)
    take_profit: Optional[Decimal] = Field(default=None, gt=0)
    is_copy_trade: bool = False
    leader_trade_id: Optional[int] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=80)


class TradeResponse(BaseModel):
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
    broker_order_id: str
    broker: str
    strategy_tag: Optional[str]
    leader_trade_id: Optional[int]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    idempotency_key: Optional[str]
    created_at: datetime
