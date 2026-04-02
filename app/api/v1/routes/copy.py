from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.copy import CopyLeaderStatsResponse, CopyRelationshipResponse, CopySubscribeRequest
from app.services.copy_service import copy_service


router = APIRouter()


@router.post("/subscribe", response_model=CopyRelationshipResponse)
def subscribe(
    payload: CopySubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return copy_service.subscribe(db, payload.leader_id, current_user)


@router.post("/unsubscribe", response_model=MessageResponse)
def unsubscribe(
    payload: CopySubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    copy_service.unsubscribe(db, payload.leader_id, current_user)
    return MessageResponse(message="Unsubscribed successfully")


@router.get("/following", response_model=list[CopyRelationshipResponse])
def following(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return copy_service.list_following(db, current_user)


@router.get("/leaders/{leader_id}/stats", response_model=CopyLeaderStatsResponse)
def leader_stats(leader_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _ = current_user
    return copy_service.get_leader_stats(db, leader_id)
