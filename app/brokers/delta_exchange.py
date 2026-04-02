from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.brokers.base import BrokerClient


class DeltaExchangeBroker(BrokerClient):
    name = "delta"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or settings.delta_api_key
        self.api_secret = api_secret or settings.delta_api_secret
        self.base_url = (base_url or settings.delta_base_url).rstrip("/")
        self.timeout = settings.delta_request_timeout_seconds

    def _sign(self, method: str, path: str, timestamp: str, body: str = "") -> str:
        payload = f"{timestamp}{method.upper()}{path}{body}"
        digest = hmac.new(self.api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
        return digest.hexdigest()

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(method, path, timestamp, body)
        return {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "content-type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None) -> Any:
        body = json.dumps(json_body or {}, separators=(",", ":")) if json_body else ""
        headers = self._headers(method, path, body)
        url = f"{self.base_url}{path}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, params=params, json=json_body, headers=headers)

        if response.status_code >= 400:
            logger.warning("Delta API error %s on %s %s: %s", response.status_code, method, path, response.text)
            response.raise_for_status()
        return response.json()

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side.lower(),
            "size": str(quantity),
            "order_type": order_type.lower(),
        }
        if order_type.upper() == "LIMIT" and price is not None:
            payload["limit_price"] = str(price)

        # Delta Exchange uses signed REST requests. Keep the endpoint isolated here so it can be adapted
        # quickly if the exchange version changes.
        return self._request("POST", "/v2/orders", json_body=payload)

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/v2/wallet/balances")

    def get_positions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v2/positions")
        if isinstance(payload, dict) and "result" in payload:
            result = payload["result"]
            return result if isinstance(result, list) else [result]
        return payload if isinstance(payload, list) else []

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")


class MockBroker(BrokerClient):
    name = "mock"

    def place_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None, order_type: str) -> dict[str, Any]:
        return {
            "order_id": f"MOCK-{int(time.time() * 1000)}",
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "price": str(price) if price is not None else None,
            "order_type": order_type,
            "status": "FILLED",
            "raw": {"source": "mock"},
        }

    def get_balance(self) -> dict[str, Any]:
        return {"broker": "mock", "balance": Decimal("100000"), "currency": "USD"}

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return {"order_id": order_id, "status": "FILLED"}