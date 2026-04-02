from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.copy_relationship import CopyRelationship
from app.models.trade import Trade
from app.models.user import User
from app.repositories.copy_repository import CopyRepository
from app.schemas.copy import CopyLeaderStatsResponse


class CopyService:
    def subscribe(self, db: Session, leader_id: int, follower: User) -> CopyRelationship:
        if leader_id == follower.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

        leader = db.scalar(select(User).where(User.id == leader_id))
        if not leader:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leader not found")

        repo = CopyRepository(db)
        existing = repo.get_relationship(leader_id, follower.id)
        if existing:
            return existing

        relationship = CopyRelationship(leader_id=leader_id, follower_id=follower.id)
        repo.create(relationship)
        db.commit()
        db.refresh(relationship)
        return relationship

    def unsubscribe(self, db: Session, leader_id: int, follower: User) -> None:
        repo = CopyRepository(db)
        relationship = repo.get_relationship(leader_id, follower.id)
        if relationship:
            db.delete(relationship)
            db.commit()

    def list_following(self, db: Session, follower: User) -> list[CopyRelationship]:
        return CopyRepository(db).list_following(follower.id)

    def get_followers(self, db: Session, leader_id: int) -> list[CopyRelationship]:
        return CopyRepository(db).list_followers(leader_id)

    def get_leader_stats(self, db: Session, leader_id: int) -> CopyLeaderStatsResponse:
        followers = self.get_followers(db, leader_id)
        trades = list(db.scalars(select(Trade).where(Trade.user_id == leader_id)).all())
        total_copied_trades = len(trades)
        winning = sum(1 for trade in trades if trade.pnl > 0)
        win_rate = (winning / total_copied_trades * 100.0) if total_copied_trades else 0.0
        return CopyLeaderStatsResponse(
            leader_id=leader_id,
            followers=len(followers),
            total_copied_trades=total_copied_trades,
            win_rate=win_rate,
        )


copy_service = CopyService()
