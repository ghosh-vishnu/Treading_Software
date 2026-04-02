from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardOverviewResponse, DashboardSummaryResponse
from app.services.dashboard_service import dashboard_service


router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_service.get_summary(db, current_user)


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return dashboard_service.get_overview(db, current_user)
