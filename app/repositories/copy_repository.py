from sqlalchemy import select

from app.models.copy_relationship import CopyRelationship
from app.repositories.base import Repository


class CopyRepository(Repository[CopyRelationship]):
    def create(self, relationship: CopyRelationship) -> CopyRelationship:
        self.db.add(relationship)
        self.db.flush()
        return relationship

    def get_relationship(self, leader_id: int, follower_id: int) -> CopyRelationship | None:
        statement = select(CopyRelationship).where(
            CopyRelationship.leader_id == leader_id,
            CopyRelationship.follower_id == follower_id,
        )
        return self.db.scalar(statement)

    def list_following(self, follower_id: int) -> list[CopyRelationship]:
        statement = select(CopyRelationship).where(CopyRelationship.follower_id == follower_id)
        return list(self.db.scalars(statement).all())

    def list_followers(self, leader_id: int) -> list[CopyRelationship]:
        statement = select(CopyRelationship).where(CopyRelationship.leader_id == leader_id)
        return list(self.db.scalars(statement).all())
