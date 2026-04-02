from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CopyRelationship(Base):
    __tablename__ = "copy_relationships"
    __table_args__ = (UniqueConstraint("leader_id", "follower_id", name="uq_leader_follower"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    leader = relationship("User", foreign_keys=[leader_id], back_populates="followers")
    follower = relationship("User", foreign_keys=[follower_id], back_populates="leaders")
