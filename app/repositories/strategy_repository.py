from sqlalchemy import select

from app.models.strategy import Strategy
from app.repositories.base import Repository


class StrategyRepository(Repository[Strategy]):
    def create(self, strategy: Strategy) -> Strategy:
        self.db.add(strategy)
        self.db.flush()
        return strategy

    def get_by_tag(self, strategy_tag: str) -> Strategy | None:
        return self.db.scalar(select(Strategy).where(Strategy.strategy_tag == strategy_tag))

    def list_for_user(self, user_id: int) -> list[Strategy]:
        statement = select(Strategy).where(Strategy.user_id == user_id).order_by(Strategy.created_at.desc())
        return list(self.db.scalars(statement).all())
