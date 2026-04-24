from __future__ import annotations

import hashlib
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.locks import LockBusyError, LockUnavailableError, RedisOrderLock
from app.core.logging import logger
from app.core.observability import metrics
from app.models.trade import Trade
from app.models.user import User
from app.repositories.trade_repository import TradeRepository
from app.schemas.trade import TradeCreateRequest
from app.services.broker_service import broker_service
from app.services.notification_service import notification_service
from app.services.risk_service import risk_service
from app.services.websocket_manager import websocket_manager


class TradeService:
    def execute_trade(self, db: Session, user: User, payload: TradeCreateRequest) -> Trade:
        trade_repo = TradeRepository(db)
        idempotency_key = self._resolve_idempotency_key(user, payload)
        if idempotency_key:
            existing = trade_repo.get_by_idempotency_key(user.id, payload.broker, idempotency_key)
            if existing is not None:
                metrics.increment("trade_idempotency_replays_total", {"broker": payload.broker})
                logger.info("Returning existing trade for idempotency key user_id=%s broker=%s", user.id, payload.broker)
                return existing

            lock_key = self._lock_key(user.id, payload.broker, idempotency_key)
            try:
                with RedisOrderLock(lock_key, settings.broker_order_lock_ttl_seconds):
                    existing = trade_repo.get_by_idempotency_key(user.id, payload.broker, idempotency_key)
                    if existing is not None:
                        metrics.increment("trade_idempotency_replays_total", {"broker": payload.broker})
                        return existing
                    return self._execute_trade_once(db, user, payload, idempotency_key)
            except LockBusyError as exc:
                existing = trade_repo.get_by_idempotency_key(user.id, payload.broker, idempotency_key)
                if existing is not None:
                    return existing
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An order with this idempotency key is already being processed.",
                ) from exc
            except LockUnavailableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Trading is temporarily unavailable because order locking is offline.",
                ) from exc

        return self._execute_trade_once(db, user, payload, None)

    def _execute_trade_once(
        self,
        db: Session,
        user: User,
        payload: TradeCreateRequest,
        idempotency_key: str | None,
    ) -> Trade:
        risk_service.validate_trade(db, user, payload.symbol, payload.quantity, payload.price)
        with metrics.timer("trade_execution_duration_seconds", {"broker": payload.broker}):
            broker_order = broker_service.place_order(
                db=db,
                user=user,
                symbol=payload.symbol,
                side=payload.side,
                quantity=payload.quantity,
                price=payload.price,
                order_type=payload.order_type,
                broker_name=payload.broker,
                idempotency_key=idempotency_key,
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
            idempotency_key=idempotency_key,
        )
        trade_repo.create(trade)
        notification_service.create_internal(
            db,
            user_id=user.id,
            category="trade",
            title="Trade Executed",
            message=f"{trade.side} {trade.quantity} {trade.symbol} via {trade.broker}",
        )
        db.commit()
        db.refresh(trade)

        if not payload.is_copy_trade:
            self._enqueue_copy_trade(trade)

        metrics.increment("trades_executed_total", {"broker": payload.broker, "status": trade.status})
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
            idempotency_key=f"copy:{leader_trade.id}:{follower.id}",
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

    @staticmethod
    def _resolve_idempotency_key(user: User, payload: TradeCreateRequest) -> str | None:
        if not payload.idempotency_key:
            return None
        key = payload.idempotency_key.strip()
        if not key:
            return None
        return key

    @staticmethod
    def _lock_key(user_id: int, broker: str, idempotency_key: str) -> str:
        raw = f"{user_id}:{broker}:{idempotency_key}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


trade_service = TradeService()
