from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.strategy import StrategyCreateRequest, StrategyResponse, StrategySignalRequest, StrategySignalResponse
from app.services.strategy_service import strategy_service


router = APIRouter()


@router.post("", response_model=StrategyResponse)
@limiter.limit("10/minute")
def create_strategy(
    request: Request,
    response: Response,
    payload: StrategyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return strategy_service.create_strategy(db, current_user, payload)


@router.post("/signal", response_model=StrategySignalResponse)
@limiter.limit("30/minute")
def send_signal(
    request: Request,
    response: Response,
    payload: StrategySignalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return strategy_service.process_signal(db, current_user, payload)
