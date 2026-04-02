from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.trade import TradeCreateRequest, TradeResponse
from app.services.trade_service import trade_service


router = APIRouter()


@router.post("/execute", response_model=TradeResponse)
@limiter.limit("30/minute")
def execute_trade(
    request: Request,
    response: Response,
    payload: TradeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return trade_service.execute_trade(db, current_user, payload)


@router.get("/me", response_model=list[TradeResponse])
def my_trades(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return trade_service.list_user_trades(db, current_user)


@router.get("/positions")
def open_positions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return trade_service.list_open_positions(db, current_user)
