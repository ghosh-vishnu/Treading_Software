from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_admin
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.academy_article import AcademyArticle
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.user import User
from app.schemas.academy import AcademyArticleCreateRequest, AcademyArticleResponse, AcademyArticleUpdateRequest
from app.schemas.common import MessageResponse
from app.schemas.common import AdminDashboardSummary
from app.schemas.strategy import AdminStrategyCreateRequest, AdminStrategyUpdateRequest, StrategyResponse
from app.services.academy_service import academy_service
from app.services.strategy_service import strategy_service


router = APIRouter()


@router.get("/summary", response_model=AdminDashboardSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user

    total_customers = db.scalar(select(func.count()).select_from(User).where(User.role == "user")) or 0
    active_customers = db.scalar(select(func.count()).select_from(User).where(User.role == "user", User.is_active.is_(True))) or 0
    total_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    total_strategies = db.scalar(select(func.count()).select_from(Strategy)) or 0
    public_strategies = db.scalar(select(func.count()).select_from(Strategy).where(Strategy.is_public.is_(True))) or 0
    total_academy_articles = db.scalar(select(func.count()).select_from(AcademyArticle)) or 0
    published_academy_articles = db.scalar(select(func.count()).select_from(AcademyArticle).where(AcademyArticle.is_published.is_(True))) or 0
    total_trades = db.scalar(select(func.count()).select_from(Trade)) or 0
    open_trades = db.scalar(
        select(func.count()).select_from(Trade).where(Trade.status.in_(["PENDING", "OPEN", "PARTIALLY_FILLED"]))
    ) or 0

    return AdminDashboardSummary(
        total_customers=total_customers,
        active_customers=active_customers,
        total_admins=total_admins,
        total_strategies=total_strategies,
        public_strategies=public_strategies,
        total_academy_articles=total_academy_articles,
        published_academy_articles=published_academy_articles,
        total_trades=total_trades,
        open_trades=open_trades,
    )


@router.get("/strategies", response_model=list[StrategyResponse])
def list_all_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    return strategy_service.list_all_strategies(db)


@router.post("/strategies", response_model=StrategyResponse)
@limiter.limit("20/minute")
def create_strategy(
    request: Request,
    response: Response,
    payload: AdminStrategyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    return strategy_service.create_admin_strategy(db, current_user, payload)


@router.patch("/strategies/{strategy_id}", response_model=StrategyResponse)
@limiter.limit("30/minute")
def update_strategy(
    strategy_id: int,
    request: Request,
    response: Response,
    payload: AdminStrategyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response, current_user)
    return strategy_service.update_admin_strategy(db, strategy_id, payload)


@router.delete("/strategies/{strategy_id}", response_model=MessageResponse)
@limiter.limit("30/minute")
def delete_strategy(
    strategy_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response, current_user)
    strategy_service.delete_admin_strategy(db, strategy_id)
    return MessageResponse(message="Strategy deleted")


@router.get("/academy/articles", response_model=list[AcademyArticleResponse])
def list_all_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    return academy_service.list_all_articles(db)


@router.post("/academy/articles", response_model=AcademyArticleResponse)
@limiter.limit("20/minute")
def create_article(
    request: Request,
    response: Response,
    payload: AcademyArticleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response, current_user)
    return academy_service.create_article(db, payload)


@router.patch("/academy/articles/{article_id}", response_model=AcademyArticleResponse)
@limiter.limit("30/minute")
def update_article(
    article_id: int,
    request: Request,
    response: Response,
    payload: AcademyArticleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response, current_user)
    return academy_service.update_article(db, article_id, payload)


@router.delete("/academy/articles/{article_id}", response_model=MessageResponse)
@limiter.limit("30/minute")
def delete_article(
    article_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response, current_user)
    academy_service.delete_article(db, article_id)
    return MessageResponse(message="Article deleted")
