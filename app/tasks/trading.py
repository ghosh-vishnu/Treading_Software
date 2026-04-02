from __future__ import annotations

from decimal import Decimal

from app.db.session import SessionLocal
from app.models.copy_relationship import CopyRelationship
from app.models.trade import Trade
from app.models.user import User
from app.services.broker_service import broker_service
from app.services.trade_service import trade_service
from app.tasks.celery_app import celery_app


@celery_app.task(name="replicate_leader_trade")
def replicate_leader_trade(leader_trade_id: int) -> dict:
    db = SessionLocal()
    try:
        leader_trade = db.get(Trade, leader_trade_id)
        if leader_trade is None:
            return {"copied": 0, "leader_trade_id": leader_trade_id}

        leader_user = db.get(User, leader_trade.user_id)
        leader_balance_payload = broker_service.get_balance(db, leader_user) if leader_user else {"balance": Decimal("1")}
        leader_balance = Decimal(str(leader_balance_payload.get("balance", "1"))) or Decimal("1")

        followers = list(db.query(CopyRelationship).filter(CopyRelationship.leader_id == leader_trade.user_id).all())
        for relation in followers:
            follower = db.get(User, relation.follower_id)
            follower_balance_payload = broker_service.get_balance(db, follower) if follower else {"balance": Decimal("1")}
            follower_balance = Decimal(str(follower_balance_payload.get("balance", "1")))
            scaling_factor = (follower_balance / leader_balance) if leader_balance > 0 else Decimal("1")
            execute_follower_copy_trade.delay(
                leader_trade_id=leader_trade.id,
                follower_id=relation.follower_id,
                scaling_factor=str(scaling_factor),
            )
        return {"copied": len(followers), "leader_trade_id": leader_trade_id}
    finally:
        db.close()


@celery_app.task(name="execute_follower_copy_trade")
def execute_follower_copy_trade(leader_trade_id: int, follower_id: int, scaling_factor: str) -> dict:
    db = SessionLocal()
    try:
        leader_trade = db.get(Trade, leader_trade_id)
        follower = db.get(User, follower_id)
        if leader_trade is None or follower is None:
            return {"status": "skipped", "reason": "leader or follower missing"}

        scale = Decimal(scaling_factor)
        copied_trade = trade_service.execute_copy_trade(db, follower, leader_trade, scale)
        return {"status": "success", "trade_id": copied_trade.id, "follower_id": follower_id}
    except Exception as exc:  # failure isolation per follower
        db.rollback()
        return {"status": "failed", "follower_id": follower_id, "error": str(exc)}
    finally:
        db.close()
