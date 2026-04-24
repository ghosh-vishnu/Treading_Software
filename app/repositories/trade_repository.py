from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models.trade import Trade
from app.repositories.base import Repository


class TradeRepository(Repository[Trade]):
    def create(self, trade: Trade) -> Trade:
        self.db.add(trade)
        self.db.flush()
        return trade

    def list_for_user(self, user_id: int) -> list[Trade]:
        statement = select(Trade).where(Trade.user_id == user_id).order_by(Trade.created_at.desc())
        return list(self.db.scalars(statement).all())

    def get_by_idempotency_key(self, user_id: int, broker: str, idempotency_key: str) -> Trade | None:
        statement = select(Trade).where(
            Trade.user_id == user_id,
            Trade.broker == broker,
            Trade.idempotency_key == idempotency_key,
        )
        return self.db.scalars(statement).one_or_none()

    def count_for_user_since(self, user_id: int, since: datetime) -> int:
        statement = select(func.count(Trade.id)).where(Trade.user_id == user_id, Trade.created_at >= since)
        return int(self.db.scalar(statement) or 0)

    def sum_pnl_for_user_since(self, user_id: int, since: datetime) -> float:
        statement = select(func.coalesce(func.sum(Trade.pnl), 0)).where(Trade.user_id == user_id, Trade.created_at >= since)
        return float(self.db.scalar(statement) or 0)
