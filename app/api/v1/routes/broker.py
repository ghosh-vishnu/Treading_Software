from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.broker import BrokerAccountResponse, BrokerBalanceResponse, BrokerConnectRequest, BrokerOrderResponse, BrokerPositionResponse
from app.services.broker_service import broker_service


router = APIRouter()


@router.post("/connect", response_model=BrokerAccountResponse)
@limiter.limit("5/minute")
def connect_broker(
    request: Request,
    response: Response,
    payload: BrokerConnectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return broker_service.connect_account(db, current_user, payload)


@router.get("/accounts", response_model=list[BrokerAccountResponse])
def get_connected_accounts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return broker_service.list_connected_accounts(db, current_user)


@router.delete("/accounts/{account_id}", response_model=MessageResponse)
def disconnect_account(account_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    broker_service.disconnect_account(db, current_user, account_id)
    return MessageResponse(message="Broker account removed successfully")


@router.get("/balance", response_model=BrokerBalanceResponse)
def get_balance(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return broker_service.get_balance(db, current_user)


@router.get("/positions", response_model=list[BrokerPositionResponse])
def get_positions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return broker_service.get_positions(db, current_user)


@router.get("/account")
def get_account_snapshot(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {
        "balance": broker_service.get_balance(db, current_user),
        "positions": broker_service.get_positions(db, current_user),
    }


@router.get("/orders/{order_id}")
def get_order_status(order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return broker_service.get_order_status(db, current_user, order_id)
