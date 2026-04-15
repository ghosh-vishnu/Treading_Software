from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BacktestRunRequest(BaseModel):
    strategy_tag: str = Field(min_length=2, max_length=120)
    symbol: str = Field(min_length=2, max_length=20)
    timeframe: str = Field(default="1h", max_length=20)
    periods: int = Field(default=200, ge=50, le=5000)
    initial_capital: float = Field(default=1000.0, gt=0)


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_tag: str
    symbol: str
    timeframe: str
    periods: int
    roi: float
    drawdown: float
    win_rate: float
    report_json: str
    created_at: datetime
