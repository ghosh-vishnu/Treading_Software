from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.academy import AcademyArticleCreateRequest, AcademyArticleResponse
from app.services.academy_service import academy_service


router = APIRouter()


@router.get("/articles", response_model=list[AcademyArticleResponse])
def list_articles(db: Session = Depends(get_db)):
    return academy_service.list_articles(db)


@router.post("/articles", response_model=AcademyArticleResponse)
def create_article(
    payload: AcademyArticleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return academy_service.create_article(db, payload)
