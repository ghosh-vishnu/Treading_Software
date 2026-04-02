from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardPnLSummary(BaseModel):
    daily: Decimal
    weekly: Decimal
    total: Decimal


class DashboardOpenPosition(BaseModel):
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    unrealized_pnl: Decimal


class DashboardStrategyPerformance(BaseModel):
    strategy_tag: str
    total_trades: int
    win_rate: Decimal
    pnl: Decimal


class DashboardSummaryResponse(BaseModel):
    total_trades: int
    cumulative_pnl: Decimal
    winning_trades: int
    losing_trades: int


class DashboardOverviewResponse(BaseModel):
    pnl: DashboardPnLSummary
    win_rate: Decimal
    trade_history_count: int
    open_positions: list[DashboardOpenPosition]
    strategy_performance: list[DashboardStrategyPerformance]
    updated_at: datetime
