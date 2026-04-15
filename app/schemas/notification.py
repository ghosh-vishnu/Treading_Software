from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreateRequest(BaseModel):
    category: str = Field(default="system", max_length=40)
    title: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=3, max_length=1000)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
