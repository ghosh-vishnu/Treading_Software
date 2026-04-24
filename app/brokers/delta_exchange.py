from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Iterable, Mapping

import httpx
from redis.exceptions import RedisError

from app.brokers.base import BrokerClient
from app.core.config import settings
from app.core.logging import logger
from app.core.observability import metrics
from app.core.redis_client import get_redis_client


class DeltaEndpoint(StrEnum):
    """Delta REST endpoints used by this adapter."""

    ORDERS = "/v2/orders"
    ORDER_DETAIL = "/v2/orders/{order_id}"
    POSITIONS = "/v2/positions"
    WALLET_BALANCES = "/v2/wallet/balances"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class NormalizedOrderStatus(StrEnum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class DeltaErrorCode(StrEnum):
    INVALID_API_KEY = "invalid_api_key"
    IP_NOT_WHITELISTED = "ip_not_whitelisted_for_api_key"
    VALIDATION_ERROR = "validation_error"
    MISSING_UNDERLYING_ASSET_SYMBOL = "missing_underlying_asset_symbol"
    MISSING_PRODUCT_ID = "missing_product_id"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class BrokerConfigurationError(RuntimeError):
    """Raised when required broker configuration is missing or unsafe."""


class BrokerPayloadError(RuntimeError):
    """Raised when the exchange response cannot be safely normalized."""


class BrokerCircuitOpenError(RuntimeError):
    """Raised when broker calls are paused after repeated transient failures."""


@dataclass(frozen=True)
class DeltaRetryPolicy:
    attempts: int
    base_delay_seconds: float
    max_delay_seconds: float


@dataclass(frozen=True)
class DeltaBrokerConfig:
    """Runtime configuration for the Delta adapter."""

    api_key: str
    api_secret: str
    base_url: str
    timeout: httpx.Timeout
    limits: httpx.Limits
    retry_policy: DeltaRetryPolicy
    preferred_balance_currencies: tuple[str, ...]
    default_currency: str
    positions_underlying_symbols: tuple[str, ...]
    quantity_precision: Decimal
    price_precision: Decimal
    circuit_breaker_enabled: bool
    circuit_breaker_failure_threshold: int
    circuit_breaker_recovery_seconds: int

    @classmethod
    def from_settings(
        cls,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
    ) -> DeltaBrokerConfig:
        resolved_key = api_key or settings.delta_api_key
        resolved_secret = api_secret or settings.delta_api_secret
        if not resolved_key or not resolved_secret:
            raise BrokerConfigurationError("Delta API key and secret must be configured before live trading.")

        return cls(
            api_key=resolved_key,
            api_secret=resolved_secret,
            base_url=(base_url or settings.delta_base_url).rstrip("/"),
            timeout=httpx.Timeout(
                timeout=settings.delta_request_timeout_seconds,
                connect=settings.delta_connect_timeout_seconds,
                pool=settings.delta_pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=settings.delta_max_connections,
                max_keepalive_connections=settings.delta_max_keepalive_connections,
            ),
            retry_policy=DeltaRetryPolicy(
                attempts=settings.delta_retry_attempts,
                base_delay_seconds=settings.delta_retry_base_delay_seconds,
                max_delay_seconds=settings.delta_retry_max_delay_seconds,
            ),
            preferred_balance_currencies=tuple(currency.upper() for currency in settings.delta_preferred_balance_currencies),
            default_currency=settings.delta_default_currency.upper(),
            positions_underlying_symbols=tuple(symbol.upper() for symbol in settings.delta_positions_underlying_symbols),
            quantity_precision=Decimal(settings.delta_quantity_precision),
            price_precision=Decimal(settings.delta_price_precision),
            circuit_breaker_enabled=settings.delta_circuit_breaker_enabled,
            circuit_breaker_failure_threshold=settings.delta_circuit_breaker_failure_threshold,
            circuit_breaker_recovery_seconds=settings.delta_circuit_breaker_recovery_seconds,
        )


@dataclass(frozen=True)
class DeltaApiErrorDetail:
    """Structured error detail parsed from Delta's error response."""

    code: str | None
    message: str | None
    context: Mapping[str, Any] = field(default_factory=dict)


class DeltaApiError(httpx.HTTPStatusError):
    """HTTP error enriched with Delta's structured error code."""

    def __init__(self, message: str, *, request: httpx.Request, response: httpx.Response, detail: DeltaApiErrorDetail) -> None:
        super().__init__(message, request=request, response=response)
        self.detail = detail
        self.error_code = detail.code


class DeltaExchangeBroker(BrokerClient):
    """Production Delta Exchange broker adapter.

    The adapter exposes async methods for FastAPI-native use and keeps sync wrappers
    for existing synchronous service code during migration.
    """

    name = "delta"
    _RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    _POSITION_SCHEMA_ERROR_CODES = {
        DeltaErrorCode.MISSING_UNDERLYING_ASSET_SYMBOL.value,
        DeltaErrorCode.MISSING_PRODUCT_ID.value,
        DeltaErrorCode.VALIDATION_ERROR.value,
    }
    _ORDER_STATUS_MAP = {
        "open": NormalizedOrderStatus.PENDING,
        "pending": NormalizedOrderStatus.PENDING,
        "new": NormalizedOrderStatus.PENDING,
        "partially_filled": NormalizedOrderStatus.PARTIALLY_FILLED,
        "partial_fill": NormalizedOrderStatus.PARTIALLY_FILLED,
        "filled": NormalizedOrderStatus.FILLED,
        "closed": NormalizedOrderStatus.FILLED,
        "cancelled": NormalizedOrderStatus.CANCELLED,
        "canceled": NormalizedOrderStatus.CANCELLED,
        "rejected": NormalizedOrderStatus.REJECTED,
    }
    _LOCAL_CIRCUITS: dict[str, dict[str, float]] = {}

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        config: DeltaBrokerConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or DeltaBrokerConfig.from_settings(api_key=api_key, api_secret=api_secret, base_url=base_url)
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> DeltaExchangeBroker:
        self._client = self._client or self._build_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying connection pool when this adapter owns it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            limits=self.config.limits,
            headers={"accept": "application/json"},
        )

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _sign(self, method: str, path: str, timestamp: str, body: str = "") -> str:
        """Create Delta HMAC signature without logging secret material."""
        payload = f"{method.upper()}{timestamp}{path}{body}"
        digest = hmac.new(
            self.config.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        )
        return digest.hexdigest()

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time()))
        return {
            "api-key": self.config.api_key,
            "timestamp": timestamp,
            "signature": self._sign(method, path, timestamp, body),
            "content-type": "application/json",
        }

    @staticmethod
    def _json_body(payload: Mapping[str, Any] | None) -> str:
        return json.dumps(payload, separators=(",", ":")) if payload else ""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        """Send a signed Delta request with retries and sanitized logging."""
        circuit_name = self._circuit_name(method, path)
        self._ensure_circuit_closed(circuit_name)
        body = self._json_body(json_body)
        headers = self._headers(method, path, body)
        retry_policy = self.config.retry_policy
        last_exc: Exception | None = None

        for attempt in range(1, retry_policy.attempts + 1):
            started_at = time.monotonic()
            try:
                response = await self._http.request(method, path, params=params, json=json_body, headers=headers)
                elapsed_seconds = time.monotonic() - started_at
                elapsed_ms = round(elapsed_seconds * 1000, 2)
                metrics.observe(
                    "broker_request_duration_seconds",
                    elapsed_seconds,
                    {"broker": self.name, "method": method.upper(), "path": self._metrics_path(path)},
                )
                metrics.increment(
                    "broker_requests_total",
                    {
                        "broker": self.name,
                        "method": method.upper(),
                        "path": self._metrics_path(path),
                        "status": str(response.status_code),
                    },
                )
                logger.info(
                    "Delta request completed method=%s path=%s status=%s elapsed_ms=%s attempt=%s",
                    method.upper(),
                    path,
                    response.status_code,
                    elapsed_ms,
                    attempt,
                )

                if response.status_code >= 400:
                    error = self._build_api_error(response)
                    if self._should_retry_response(response.status_code, attempt):
                        await self._sleep_before_retry(attempt)
                        continue
                    if self._is_circuit_failure_status(response.status_code):
                        self._record_circuit_failure(circuit_name)
                    raise error

                self._record_circuit_success(circuit_name)
                return self._parse_json_response(response)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                metrics.increment(
                    "broker_request_errors_total",
                    {
                        "broker": self.name,
                        "method": method.upper(),
                        "path": self._metrics_path(path),
                        "error_type": type(exc).__name__,
                    },
                )
                logger.warning(
                    "Delta transient request failure method=%s path=%s attempt=%s error_type=%s",
                    method.upper(),
                    path,
                    attempt,
                    type(exc).__name__,
                )
                if attempt >= retry_policy.attempts:
                    self._record_circuit_failure(circuit_name)
                    raise
                await self._sleep_before_retry(attempt)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Delta request failed without an exception.")

    def _ensure_circuit_closed(self, circuit_name: str) -> None:
        if not self.config.circuit_breaker_enabled:
            return
        opened_until = self._get_circuit_open_until(circuit_name)
        if opened_until > time.time():
            metrics.increment("broker_circuit_open_total", {"broker": self.name, "circuit": circuit_name})
            raise BrokerCircuitOpenError(
                f"Delta circuit '{circuit_name}' is open until {int(opened_until)} after repeated transient failures."
            )

    def _record_circuit_success(self, circuit_name: str) -> None:
        if not self.config.circuit_breaker_enabled:
            return
        try:
            redis = get_redis_client()
            redis.delete(self._circuit_failures_key(circuit_name), self._circuit_open_key(circuit_name))
        except RedisError:
            self._LOCAL_CIRCUITS.pop(circuit_name, None)

    def _record_circuit_failure(self, circuit_name: str) -> None:
        if not self.config.circuit_breaker_enabled:
            return
        try:
            redis = get_redis_client()
            failures = int(redis.incr(self._circuit_failures_key(circuit_name)))
            redis.expire(self._circuit_failures_key(circuit_name), self.config.circuit_breaker_recovery_seconds)
            if failures >= self.config.circuit_breaker_failure_threshold:
                opened_until = time.time() + self.config.circuit_breaker_recovery_seconds
                redis.set(
                    self._circuit_open_key(circuit_name),
                    str(opened_until),
                    ex=self.config.circuit_breaker_recovery_seconds,
                )
                metrics.increment("broker_circuit_transitions_total", {"broker": self.name, "circuit": circuit_name, "state": "open"})
                logger.error("Delta circuit opened circuit=%s failures=%s", circuit_name, failures)
        except RedisError as exc:
            state = self._LOCAL_CIRCUITS.setdefault(circuit_name, {"failures": 0, "opened_until": 0})
            state["failures"] += 1
            if state["failures"] >= self.config.circuit_breaker_failure_threshold:
                state["opened_until"] = time.time() + self.config.circuit_breaker_recovery_seconds
            logger.warning("Circuit breaker Redis write failed circuit=%s error_type=%s", circuit_name, type(exc).__name__)

    def _get_circuit_open_until(self, circuit_name: str) -> float:
        try:
            value = get_redis_client().get(self._circuit_open_key(circuit_name))
            return float(value) if value else 0
        except (RedisError, ValueError):
            return self._LOCAL_CIRCUITS.get(circuit_name, {}).get("opened_until", 0)

    def _circuit_name(self, method: str, path: str) -> str:
        return f"{method.upper()}:{self._metrics_path(path)}"

    @staticmethod
    def _metrics_path(path: str) -> str:
        if path.startswith("/v2/orders/"):
            return "/v2/orders/{order_id}"
        return path

    def _circuit_failures_key(self, circuit_name: str) -> str:
        return f"broker:circuit:{self.name}:{circuit_name}:failures"

    def _circuit_open_key(self, circuit_name: str) -> str:
        return f"broker:circuit:{self.name}:{circuit_name}:open_until"

    def _is_circuit_failure_status(self, status_code: int) -> bool:
        return status_code in self._RETRYABLE_STATUS_CODES

    def _should_retry_response(self, status_code: int, attempt: int) -> bool:
        return status_code in self._RETRYABLE_STATUS_CODES and attempt < self.config.retry_policy.attempts

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(
            self.config.retry_policy.max_delay_seconds,
            self.config.retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
        )
        await asyncio.sleep(delay + random.uniform(0, delay / 4))

    @staticmethod
    def _parse_json_response(response: httpx.Response) -> Any:
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise BrokerPayloadError("Delta returned a non-JSON response.") from exc

    def _build_api_error(self, response: httpx.Response) -> DeltaApiError:
        detail = self._extract_error_detail(response)
        logger.warning(
            "Delta API error status=%s code=%s path=%s",
            response.status_code,
            detail.code,
            response.request.url.path,
        )
        return DeltaApiError(
            f"Delta API error status={response.status_code} code={detail.code or 'unknown'}",
            request=response.request,
            response=response,
            detail=detail,
        )

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> DeltaApiErrorDetail:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return DeltaApiErrorDetail(code=None, message=None)

        if not isinstance(payload, dict):
            return DeltaApiErrorDetail(code=None, message=None)

        error = payload.get("error")
        if isinstance(error, dict):
            context = error.get("context") if isinstance(error.get("context"), dict) else {}
            return DeltaApiErrorDetail(
                code=str(error.get("code")) if error.get("code") else None,
                message=str(error.get("message")) if error.get("message") else None,
                context=context,
            )

        return DeltaApiErrorDetail(
            code=str(payload.get("code")) if payload.get("code") else None,
            message=str(payload.get("message")) if payload.get("message") else None,
        )

    async def place_order_async(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Validate, submit, and normalize an order."""
        request = self._build_order_payload(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            idempotency_key=idempotency_key,
        )
        payload = await self._request("POST", DeltaEndpoint.ORDERS.value, json_body=request)
        return self._normalize_order_response(payload)

    def _build_order_payload(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        clean_symbol = self._validate_symbol(symbol)
        clean_side = self._validate_side(side)
        clean_order_type = self._validate_order_type(order_type)
        clean_quantity = self._validate_decimal(quantity, "quantity", self.config.quantity_precision, must_be_positive=True)

        payload: dict[str, Any] = {
            "product_symbol": clean_symbol,
            "side": clean_side.value,
            "size": str(clean_quantity),
            "order_type": clean_order_type.value,
        }
        if idempotency_key:
            payload["client_order_id"] = self._validate_idempotency_key(idempotency_key)

        if clean_order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit orders require a price.")
            payload["limit_price"] = str(self._validate_decimal(price, "price", self.config.price_precision, must_be_positive=True))
        elif price is not None:
            logger.info("Ignoring price for Delta market order symbol=%s", clean_symbol)

        return payload

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> str:
        clean_key = idempotency_key.strip()
        if not clean_key:
            raise ValueError("idempotency_key cannot be blank.")
        if len(clean_key) > 80:
            raise ValueError("idempotency_key cannot exceed 80 characters.")
        return clean_key

    @staticmethod
    def _validate_symbol(symbol: str) -> str:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            raise ValueError("Order symbol is required.")
        return clean_symbol

    @staticmethod
    def _validate_side(side: str) -> OrderSide:
        try:
            return OrderSide(side.strip().lower())
        except ValueError as exc:
            allowed = ", ".join(item.value.upper() for item in OrderSide)
            raise ValueError(f"Unsupported order side '{side}'. Allowed values: {allowed}.") from exc

    @staticmethod
    def _validate_order_type(order_type: str) -> OrderType:
        try:
            return OrderType(order_type.strip().lower())
        except ValueError as exc:
            allowed = ", ".join(item.value.upper() for item in OrderType)
            raise ValueError(f"Unsupported order type '{order_type}'. Allowed values: {allowed}.") from exc

    @staticmethod
    def _validate_decimal(value: Decimal, field_name: str, precision: Decimal, *, must_be_positive: bool) -> Decimal:
        try:
            decimal_value = Decimal(str(value))
            quantized = decimal_value.quantize(precision)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid {field_name}: {value!r}.") from exc

        if must_be_positive and quantized <= 0:
            raise ValueError(f"{field_name.capitalize()} must be greater than zero.")
        if decimal_value != quantized:
            raise ValueError(f"{field_name.capitalize()} precision exceeds allowed step {precision}.")
        return quantized

    async def get_balance_async(self) -> dict[str, Any]:
        """Fetch and normalize the preferred wallet balance."""
        payload = await self._request("GET", DeltaEndpoint.WALLET_BALANCES.value)
        return self._normalize_balance(payload)

    async def get_positions_async(self) -> list[dict[str, Any]]:
        """Fetch positions and normalize them into the internal broker contract."""
        try:
            payload = await self._request("GET", DeltaEndpoint.POSITIONS.value)
            return self._normalize_positions(self._extract_records(payload))
        except DeltaApiError as exc:
            if not self._requires_position_underlying(exc):
                raise
            return await self._get_positions_by_configured_underlyings()

    async def _get_positions_by_configured_underlyings(self) -> list[dict[str, Any]]:
        if not self.config.positions_underlying_symbols:
            logger.warning("Delta positions endpoint requires configured underlying symbols, but none are configured.")
            return []

        merged_records: list[Mapping[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for underlying in self.config.positions_underlying_symbols:
            try:
                records = await self._request_positions_by_underlying(underlying)
            except DeltaApiError as exc:
                logger.warning("Delta positions fallback failed underlying=%s code=%s", underlying, exc.error_code)
                continue

            for record in records:
                key = self._position_identity(record)
                if key in seen:
                    continue
                seen.add(key)
                merged_records.append(record)

        return self._normalize_positions(merged_records)

    async def _request_positions_by_underlying(self, underlying_symbol: str) -> list[Mapping[str, Any]]:
        payload = await self._request(
            "GET",
            DeltaEndpoint.POSITIONS.value,
            params={"underlying_asset_symbol": underlying_symbol},
        )
        return self._extract_records(payload)

    def _requires_position_underlying(self, exc: DeltaApiError) -> bool:
        if exc.error_code not in self._POSITION_SCHEMA_ERROR_CODES:
            return False
        context_keys = {str(key) for key in exc.detail.context.keys()}
        return not context_keys or bool({"underlying_asset_symbol", "product_id"} & context_keys)

    @staticmethod
    def _extract_records(payload: Any) -> list[Mapping[str, Any]]:
        result = payload.get("result") if isinstance(payload, dict) else payload
        if isinstance(result, list):
            return [item for item in result if isinstance(item, Mapping)]
        if isinstance(result, Mapping):
            return [result]
        return []

    def _normalize_balance(self, payload: Any) -> dict[str, Any]:
        records = self._extract_records(payload)
        if not records and isinstance(payload, Mapping) and {"broker", "balance", "currency"}.issubset(payload.keys()):
            return dict(payload)

        if not records:
            raise BrokerPayloadError("Delta balance response did not include wallet records.")

        preferred = self._select_preferred_balance_record(records)
        currency = self._extract_first(preferred, ("asset_symbol", "currency"))
        if not currency:
            raise BrokerPayloadError("Delta balance record is missing currency.")

        balance_value = self._extract_first(preferred, ("balance", "available_balance", "wallet_balance", "equity"))
        if balance_value is None:
            raise BrokerPayloadError(f"Delta balance record is missing a balance value for {currency}.")

        available_value = self._extract_first(preferred, ("available_balance",))
        return {
            "broker": self.name,
            "balance": self._to_decimal(balance_value, "balance"),
            "currency": str(currency).upper(),
            "available_balance": self._to_decimal(available_value, "available_balance") if available_value is not None else None,
            "raw": {"source": self.name},
        }

    def _select_preferred_balance_record(self, records: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
        record_list = list(records)
        by_currency = {
            str(self._extract_first(record, ("asset_symbol", "currency")) or "").upper(): record
            for record in record_list
        }
        for currency in self.config.preferred_balance_currencies:
            if currency in by_currency:
                return by_currency[currency]
        if self.config.default_currency in by_currency:
            return by_currency[self.config.default_currency]
        return record_list[0]

    def _normalize_positions(self, records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in records:
            symbol = self._extract_first(record, ("symbol", "product_symbol", "contract"))
            if not symbol:
                logger.warning("Skipping Delta position without symbol keys=%s", sorted(str(key) for key in record.keys()))
                continue

            quantity = self._extract_first(record, ("size", "quantity", "position_size"))
            if quantity is None:
                logger.warning("Skipping Delta position without quantity symbol=%s", symbol)
                continue

            normalized.append(
                {
                    "broker": self.name,
                    "symbol": str(symbol).upper(),
                    "quantity": self._to_decimal(quantity, "quantity"),
                    "avg_entry_price": self._to_decimal(
                        self._extract_first(record, ("entry_price", "avg_entry_price", "average_price")) or 0,
                        "avg_entry_price",
                    ),
                    "unrealized_pnl": self._to_decimal(
                        self._extract_first(record, ("unrealized_pnl", "pnl", "mark_pnl")) or 0,
                        "unrealized_pnl",
                    ),
                    "raw": {"source": self.name},
                }
            )
        return normalized

    async def get_order_status_async(self, order_id: str) -> dict[str, Any]:
        """Fetch and normalize order status."""
        clean_order_id = order_id.strip()
        if not clean_order_id:
            raise ValueError("order_id is required.")
        payload = await self._request("GET", DeltaEndpoint.ORDER_DETAIL.value.format(order_id=clean_order_id))
        return self._normalize_order_response(payload)

    def _normalize_order_response(self, payload: Any) -> dict[str, Any]:
        result = payload.get("result") if isinstance(payload, Mapping) else payload
        if not isinstance(result, Mapping):
            raise BrokerPayloadError("Delta order response did not include an order object.")

        order_id = self._extract_first(result, ("id", "order_id", "client_order_id"))
        symbol = self._extract_first(result, ("product_symbol", "symbol", "contract"))
        status = self._normalize_order_status(self._extract_first(result, ("state", "status", "order_state")))

        return {
            "broker": self.name,
            "order_id": str(order_id) if order_id is not None else "",
            "symbol": str(symbol).upper() if symbol else "",
            "side": str(self._extract_first(result, ("side",)) or "").upper(),
            "quantity": str(self._extract_first(result, ("size", "quantity")) or ""),
            "filled_quantity": str(self._extract_first(result, ("filled_size", "filled_quantity", "filled")) or "0"),
            "remaining_quantity": str(self._extract_first(result, ("unfilled_size", "remaining_quantity", "remaining")) or "0"),
            "price": str(self._extract_first(result, ("limit_price", "price", "average_fill_price")) or ""),
            "order_type": str(self._extract_first(result, ("order_type", "type")) or "").upper(),
            "status": status.value,
            "raw": {"source": self.name, "payload": result},
        }

    def _normalize_order_status(self, status: Any) -> NormalizedOrderStatus:
        if status is None:
            return NormalizedOrderStatus.UNKNOWN
        return self._ORDER_STATUS_MAP.get(str(status).strip().lower(), NormalizedOrderStatus.UNKNOWN)

    @staticmethod
    def _extract_first(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
        for key in keys:
            value = record.get(key)
            if value is not None and value != "":
                return value
        return None

    @staticmethod
    def _position_identity(record: Mapping[str, Any]) -> tuple[str, str]:
        product_id = record.get("product_id") or record.get("id") or ""
        symbol = record.get("product_symbol") or record.get("symbol") or record.get("contract") or ""
        return str(product_id), str(symbol)

    @staticmethod
    def _to_decimal(value: Any, field_name: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise BrokerPayloadError(f"Invalid decimal value for {field_name}: {value!r}.") from exc

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._run_sync(self.place_order_async(symbol, side, quantity, price, order_type, idempotency_key))

    def get_balance(self) -> dict[str, Any]:
        return self._run_sync(self.get_balance_async())

    def get_positions(self) -> list[dict[str, Any]]:
        return self._run_sync(self.get_positions_async())

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return self._run_sync(self.get_order_status_async(order_id))

    def _run_sync(self, coroutine: Any) -> Any:
        """Compatibility bridge for the current synchronous service layer."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run_and_close(coroutine))
        raise RuntimeError("Use the async broker methods when calling from an async event loop.")

    async def _run_and_close(self, coroutine: Any) -> Any:
        try:
            return await coroutine
        finally:
            await self.aclose()


class MockBroker(BrokerClient):
    """Realistic broker simulator for local development and tests."""

    name = "mock"
    _VALID_STATUSES = {
        NormalizedOrderStatus.FILLED.value,
        NormalizedOrderStatus.PENDING.value,
        NormalizedOrderStatus.REJECTED.value,
        NormalizedOrderStatus.CANCELLED.value,
        NormalizedOrderStatus.PARTIALLY_FILLED.value,
    }

    def __init__(
        self,
        default_balance: Decimal | None = None,
        currency: str | None = None,
        default_order_status: str | None = None,
    ) -> None:
        self.balance = default_balance or Decimal(settings.mock_broker_default_balance)
        self.currency = (currency or settings.mock_broker_default_currency).upper()
        self.default_order_status = self._normalize_mock_status(default_order_status or settings.mock_broker_default_order_status)
        self._orders: dict[str, dict[str, Any]] = {}

    async def place_order_async(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        clean_quantity = Decimal(str(quantity))
        if clean_quantity <= 0:
            status = NormalizedOrderStatus.REJECTED.value
        else:
            status = self.default_order_status

        filled_quantity = self._filled_quantity(clean_quantity, status)
        order = {
            "broker": self.name,
            "order_id": idempotency_key or f"MOCK-{int(time.time() * 1000)}",
            "symbol": symbol.strip().upper(),
            "side": side.strip().upper(),
            "quantity": str(clean_quantity),
            "filled_quantity": str(filled_quantity),
            "remaining_quantity": str(clean_quantity - filled_quantity),
            "price": str(price) if price is not None else "",
            "order_type": order_type.strip().upper(),
            "status": status,
            "raw": {"source": self.name},
        }
        self._orders[order["order_id"]] = order
        return order

    async def get_balance_async(self) -> dict[str, Any]:
        return {
            "broker": self.name,
            "balance": self.balance,
            "currency": self.currency,
            "available_balance": self.balance,
        }

    async def get_positions_async(self) -> list[dict[str, Any]]:
        positions: dict[str, Decimal] = {}
        for order in self._orders.values():
            if order["status"] not in {NormalizedOrderStatus.FILLED.value, NormalizedOrderStatus.PARTIALLY_FILLED.value}:
                continue
            signed_qty = Decimal(order["filled_quantity"])
            if order["side"] == "SELL":
                signed_qty *= Decimal("-1")
            positions[order["symbol"]] = positions.get(order["symbol"], Decimal("0")) + signed_qty

        return [
            {
                "broker": self.name,
                "symbol": symbol,
                "quantity": quantity,
                "avg_entry_price": Decimal("0"),
                "unrealized_pnl": Decimal("0"),
            }
            for symbol, quantity in positions.items()
            if quantity != 0
        ]

    async def get_order_status_async(self, order_id: str) -> dict[str, Any]:
        return self._orders.get(
            order_id,
            {
                "broker": self.name,
                "order_id": order_id,
                "status": NormalizedOrderStatus.UNKNOWN.value,
                "raw": {"source": self.name},
            },
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(self.place_order_async(symbol, side, quantity, price, order_type, idempotency_key))

    def get_balance(self) -> dict[str, Any]:
        return asyncio.run(self.get_balance_async())

    def get_positions(self) -> list[dict[str, Any]]:
        return asyncio.run(self.get_positions_async())

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return asyncio.run(self.get_order_status_async(order_id))

    def _normalize_mock_status(self, status: str) -> str:
        normalized = status.strip().upper()
        if normalized not in self._VALID_STATUSES:
            raise ValueError(f"Unsupported mock broker status '{status}'.")
        return normalized

    @staticmethod
    def _filled_quantity(quantity: Decimal, status: str) -> Decimal:
        if status == NormalizedOrderStatus.FILLED.value:
            return quantity
        if status == NormalizedOrderStatus.PARTIALLY_FILLED.value:
            return (quantity / Decimal("2")).quantize(Decimal("0.0001"))
        return Decimal("0")
