from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AcademyArticleCreateRequest(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    slug: str = Field(min_length=3, max_length=255)
    category: str = Field(default="general", max_length=80)
    summary: str = Field(min_length=10, max_length=500)
    content_markdown: str = Field(min_length=20)
    is_published: bool = True


class AcademyArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=255)
    slug: str | None = Field(default=None, min_length=3, max_length=255)
    category: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, min_length=10, max_length=500)
    content_markdown: str | None = Field(default=None, min_length=20)
    is_published: bool | None = None


class AcademyArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    category: str
    summary: str
    content_markdown: str
    is_published: bool
    created_at: datetime
    updated_at: datetime
