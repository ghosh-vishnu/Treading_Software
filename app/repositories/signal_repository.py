from sqlalchemy import select

from app.models.signal import Signal
from app.repositories.base import Repository


class SignalRepository(Repository[Signal]):
    def create(self, signal: Signal) -> Signal:
        self.db.add(signal)
        self.db.flush()
        return signal

    def list_for_user(self, user_id: int) -> list[Signal]:
        statement = select(Signal).where(Signal.user_id == user_id).order_by(Signal.created_at.desc())
        return list(self.db.scalars(statement).all())
