from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session


ModelType = TypeVar("ModelType")


class Repository(Generic[ModelType]):
    def __init__(self, db: Session) -> None:
        self.db = db
