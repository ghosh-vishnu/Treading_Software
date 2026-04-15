from sqlalchemy import select

from app.models.broker_account import BrokerAccount
from app.repositories.base import Repository


class BrokerRepository(Repository[BrokerAccount]):
    def create(self, account: BrokerAccount) -> BrokerAccount:
        self.db.add(account)
        self.db.flush()
        return account

    def get_active_for_user(self, user_id: int, broker_name: str | None = None) -> BrokerAccount | None:
        statement = select(BrokerAccount).where(BrokerAccount.user_id == user_id, BrokerAccount.is_active.is_(True))
        if broker_name:
            statement = statement.where(BrokerAccount.broker_name == broker_name)
        return self.db.scalar(statement.order_by(BrokerAccount.updated_at.desc()))

    def list_active_for_user(self, user_id: int) -> list[BrokerAccount]:
        statement = (
            select(BrokerAccount)
            .where(BrokerAccount.user_id == user_id, BrokerAccount.is_active.is_(True))
            .order_by(BrokerAccount.updated_at.desc())
        )
        return list(self.db.scalars(statement).all())
