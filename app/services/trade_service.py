from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.copy_relationship import CopyRelationship
from app.models.trade import Trade
from app.models.user import User
from app.repositories.copy_repository import CopyRepository
from app.repositories.trade_repository import TradeRepository
from app.schemas.trade import TradeCreateRequest
from app.services.broker_service import broker_service
from app.services.risk_service import risk_service
from app.services.websocket_manager import websocket_manager


class TradeService:
    def execute_trade(self, db: Session, user: User, payload: TradeCreateRequest) -> Trade:
        risk_service.validate_trade(db, user, payload.symbol, payload.quantity, payload.price)
        broker_order = broker_service.place_order(
            db=db,
            user=user,
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            price=payload.price,
            order_type=payload.order_type,
            broker_name=payload.broker,
        )

        trade_repo = TradeRepository(db)
        trade = Trade(
            user_id=user.id,
            symbol=payload.symbol.upper(),
            side=payload.side,
            quantity=payload.quantity,
            price=payload.price,
            order_type=payload.order_type,
            status=broker_order.get("status", "PENDING"),
            pnl=self._estimate_trade_pnl(payload.side, payload.quantity, payload.price),
            broker_order_id=str(broker_order.get("order_id") or broker_order.get("broker_order_id") or ""),
            broker=payload.broker,
            strategy_tag=payload.strategy_tag,
            leader_trade_id=payload.leader_trade_id,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
        )
        trade_repo.create(trade)
        db.commit()
        db.refresh(trade)

        if not payload.is_copy_trade:
            self._enqueue_copy_trade(trade)

        return trade

    def execute_copy_trade(
        self,
        db: Session,
        follower: User,
        leader_trade: Trade,
        scaling_factor: Decimal,
    ) -> Trade:
        quantity = (Decimal(str(leader_trade.quantity)) * scaling_factor).quantize(Decimal("0.0001"))
        payload = TradeCreateRequest(
            symbol=leader_trade.symbol,
            side=leader_trade.side,  # type: ignore[arg-type]
            quantity=quantity,
            price=Decimal(str(leader_trade.price)),
            order_type=leader_trade.order_type,  # type: ignore[arg-type]
            broker=leader_trade.broker,  # type: ignore[arg-type]
            strategy_tag=f"copy:{leader_trade.strategy_tag or 'leader'}",
            stop_loss=leader_trade.stop_loss,
            take_profit=leader_trade.take_profit,
            is_copy_trade=True,
            leader_trade_id=leader_trade.id,
        )
        return self.execute_trade(db, follower, payload)

    def list_user_trades(self, db: Session, user: User) -> list[Trade]:
        return TradeRepository(db).list_for_user(user.id)

    def list_open_positions(self, db: Session, user: User) -> list[dict]:
        positions = broker_service.get_positions(db, user)
        return positions

    def _enqueue_copy_trade(self, trade: Trade) -> None:
        from app.tasks.trading import replicate_leader_trade

        replicate_leader_trade.delay(trade.id)

    def _estimate_trade_pnl(self, side: str, quantity: Decimal, price: Decimal) -> Decimal:
        direction = Decimal("1") if side == "SELL" else Decimal("-1")
        return (direction * quantity * (price * Decimal("0.0025"))).quantize(Decimal("0.0001"))


trade_service = TradeService()
