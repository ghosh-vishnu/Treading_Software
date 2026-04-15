from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.kyc import KYCResponse, KYCSubmitRequest
from app.services.kyc_service import kyc_service


router = APIRouter()


@router.post("/submit", response_model=KYCResponse)
def submit_kyc(
    payload: KYCSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return kyc_service.submit(db, current_user, payload)


@router.get("/status", response_model=KYCResponse | None)
def get_kyc_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return kyc_service.get_status(db, current_user)
