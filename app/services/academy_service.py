from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academy_article import AcademyArticle
from app.schemas.academy import AcademyArticleCreateRequest, AcademyArticleResponse


class AcademyService:
    def list_articles(self, db: Session) -> list[AcademyArticleResponse]:
        articles = list(
            db.scalars(
                select(AcademyArticle)
                .where(AcademyArticle.is_published.is_(True))
                .order_by(AcademyArticle.created_at.desc())
            ).all()
        )
        return [AcademyArticleResponse.model_validate(item) for item in articles]

    def create_article(self, db: Session, payload: AcademyArticleCreateRequest) -> AcademyArticleResponse:
        existing = db.scalar(select(AcademyArticle).where(AcademyArticle.slug == payload.slug))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Article slug already exists")

        article = AcademyArticle(
            title=payload.title,
            slug=payload.slug,
            category=payload.category,
            summary=payload.summary,
            content_markdown=payload.content_markdown,
            is_published=payload.is_published,
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return AcademyArticleResponse.model_validate(article)


academy_service = AcademyService()
