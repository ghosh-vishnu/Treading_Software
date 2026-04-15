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
        # Delta signs as METHOD + TIMESTAMP + PATH + BODY.
        payload = f"{method.upper()}{timestamp}{path}{body}"
        digest = hmac.new(self.api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
        return digest.hexdigest()

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        # Delta expects UNIX timestamp in seconds for request signing.
        timestamp = str(int(time.time()))
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
        payload = self._request("GET", "/v2/wallet/balances")

        # Normalize Delta payload to the app's broker balance contract.
        if isinstance(payload, dict):
            if {"broker", "balance", "currency"}.issubset(payload.keys()):
                return payload

            result = payload.get("result")
            if isinstance(result, list) and result:
                preferred = next(
                    (item for item in result if str(item.get("asset_symbol", "")).upper() in {"USD", "USDT"}),
                    result[0],
                )
                balance_value = (
                    preferred.get("balance")
                    or preferred.get("available_balance")
                    or preferred.get("wallet_balance")
                    or preferred.get("equity")
                    or 0
                )
                available_value = preferred.get("available_balance")
                return {
                    "broker": "delta",
                    "balance": Decimal(str(balance_value)),
                    "currency": preferred.get("asset_symbol") or preferred.get("currency") or "USD",
                    "available_balance": Decimal(str(available_value)) if available_value is not None else None,
                }

            if isinstance(result, dict):
                balance_value = (
                    result.get("balance")
                    or result.get("available_balance")
                    or result.get("wallet_balance")
                    or result.get("equity")
                    or 0
                )
                available_value = result.get("available_balance")
                return {
                    "broker": "delta",
                    "balance": Decimal(str(balance_value)),
                    "currency": result.get("asset_symbol") or result.get("currency") or "USD",
                    "available_balance": Decimal(str(available_value)) if available_value is not None else None,
                }

        return {"broker": "delta", "balance": Decimal("0"), "currency": "USD"}

    def get_positions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v2/positions")
        if isinstance(payload, dict) and "result" in payload:
            result = payload["result"]
            records = result if isinstance(result, list) else [result]
        elif isinstance(payload, list):
            records = payload
        else:
            records = []

        normalized: list[dict[str, Any]] = []
        for item in records:
            if not isinstance(item, dict):
                continue

            symbol = item.get("symbol") or item.get("product_symbol") or item.get("contract") or "UNKNOWN"
            quantity = item.get("size") or item.get("quantity") or item.get("position_size") or 0
            avg_entry_price = item.get("entry_price") or item.get("avg_entry_price") or item.get("average_price") or 0
            unrealized_pnl = item.get("unrealized_pnl") or item.get("pnl") or item.get("mark_pnl") or 0

            normalized.append(
                {
                    "symbol": str(symbol),
                    "quantity": Decimal(str(quantity)),
                    "avg_entry_price": Decimal(str(avg_entry_price)),
                    "unrealized_pnl": Decimal(str(unrealized_pnl)),
                }
            )

        return normalized

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