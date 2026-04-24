from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class BrokerClient(ABC):
    name: str

    @abstractmethod
    async def place_order_async(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_balance_async(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_positions_async(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_order_status_async(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError
