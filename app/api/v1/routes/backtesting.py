from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.backtesting import BacktestRunRequest, BacktestRunResponse
from app.services.backtesting_service import backtesting_service


router = APIRouter()


@router.post("/run", response_model=BacktestRunResponse)
def run_backtest(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return backtesting_service.run(db, current_user, payload)
