from sqlalchemy import select

from app.models.user import User
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id))
