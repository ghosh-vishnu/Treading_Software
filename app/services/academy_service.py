from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academy_article import AcademyArticle
from app.schemas.academy import AcademyArticleCreateRequest, AcademyArticleResponse, AcademyArticleUpdateRequest


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

    def get_article_by_slug(self, db: Session, slug: str) -> AcademyArticleResponse:
        article = db.scalar(
            select(AcademyArticle).where(
                AcademyArticle.slug == slug,
                AcademyArticle.is_published.is_(True),
            )
        )
        if not article:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        return AcademyArticleResponse.model_validate(article)

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

    def list_all_articles(self, db: Session) -> list[AcademyArticleResponse]:
        articles = list(db.scalars(select(AcademyArticle).order_by(AcademyArticle.created_at.desc())).all())
        return [AcademyArticleResponse.model_validate(item) for item in articles]

    def update_article(self, db: Session, article_id: int, payload: AcademyArticleUpdateRequest) -> AcademyArticleResponse:
        article = db.scalar(select(AcademyArticle).where(AcademyArticle.id == article_id))
        if not article:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

        updates = payload.model_dump(exclude_unset=True)
        new_slug = updates.get("slug")
        if new_slug and new_slug != article.slug:
            existing = db.scalar(select(AcademyArticle).where(AcademyArticle.slug == new_slug))
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Article slug already exists")

        for field_name, value in updates.items():
            setattr(article, field_name, value)

        db.add(article)
        db.commit()
        db.refresh(article)
        return AcademyArticleResponse.model_validate(article)

    def delete_article(self, db: Session, article_id: int) -> None:
        article = db.scalar(select(AcademyArticle).where(AcademyArticle.id == article_id))
        if not article:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        db.delete(article)
        db.commit()


academy_service = AcademyService()
