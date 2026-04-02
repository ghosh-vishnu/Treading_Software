from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CopySubscribeRequest(BaseModel):
    leader_id: int = Field(gt=0)


class CopyExecutionRequest(BaseModel):
    leader_trade_id: int = Field(gt=0)
    follower_id: int = Field(gt=0)
    scaling_factor: float = Field(default=1.0, gt=0)


class CopyRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    leader_id: int
    follower_id: int
    created_at: datetime


class CopyLeaderStatsResponse(BaseModel):
    leader_id: int
    followers: int
    total_copied_trades: int
    win_rate: float
