from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class BrokerClient(ABC):
    name: str

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError