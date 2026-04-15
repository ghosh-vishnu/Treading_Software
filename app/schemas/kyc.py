from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KYCSubmitRequest(BaseModel):
    document_type: str = Field(min_length=2, max_length=50)
    document_id: str = Field(min_length=3, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class KYCResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    document_type: str
    document_id: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    verified_at: datetime | None = None
