from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.brokers.base import BrokerClient
from app.brokers.delta_exchange import MockBroker
from app.brokers.factory import get_broker_client
from app.core.security import decrypt_sensitive_value, encrypt_sensitive_value
from app.models.broker_account import BrokerAccount
from app.models.user import User
from app.repositories.broker_repository import BrokerRepository
from app.schemas.broker import BrokerAccountResponse, BrokerConnectRequest


class BrokerService:
    @staticmethod
    def _parse_metadata(metadata_json: str | None) -> dict[str, Any]:
        if not metadata_json:
            return {}
        try:
            parsed = json.loads(metadata_json)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _extract_error_payload(exc: Exception) -> dict[str, Any] | None:
        response = getattr(exc, "response", None)
        text = getattr(response, "text", None)
        if not text:
            return None
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None

    @classmethod
    def _extract_error_code(cls, exc: Exception) -> str | None:
        payload = cls._extract_error_payload(exc)
        if not payload:
            return None
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            return str(code) if code else None
        return None

    @classmethod
    def _build_connect_error_message(cls, exc: Exception) -> str:
        payload = cls._extract_error_payload(exc)
        if payload:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = str(error.get("code") or "").strip()
            context = error.get("context") if isinstance(error.get("context"), dict) else {}

            if code == "ip_not_whitelisted_for_api_key":
                client_ip = context.get("client_ip")
                if isinstance(client_ip, str) and client_ip:
                    return (
                        f"Broker authentication failed: API key IP whitelist mismatch. "
                        f"Add this server IP to your Delta API whitelist: {client_ip}."
                    )
                return "Broker authentication failed: API key IP whitelist mismatch. Add this server IP to your Delta API whitelist."

            if code == "invalid_api_key":
                return "Broker authentication failed: Invalid API key or secret."

            if code:
                return f"Broker authentication failed: {code}."

        detail = cls._extract_error_detail(exc)
        if detail:
            return f"Broker authentication failed: {detail}"

        return f"Broker connection validation failed: {str(exc)}"

    @staticmethod
    def _extract_error_detail(exc: Exception) -> str | None:
        response = getattr(exc, "response", None)
        text = getattr(response, "text", None)
        if not text:
            return None
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    code = error.get("code")
                    context = error.get("context")
                    if code and context:
                        return f"{code}: {context}"
                    if code:
                        return str(code)
            return text
        except json.JSONDecodeError:
            return text

    def _raise_broker_exception(self, exc: Exception, action: str) -> None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        detail = self._extract_error_detail(exc)
        message = detail or str(exc)

        if status_code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Broker {action} failed: {message}. Check API key permissions and IP whitelist.",
            ) from exc

        if status_code and 400 <= int(status_code) < 500:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Broker {action} failed: {message}") from exc

        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker {action} unavailable") from exc

    @staticmethod
    def _build_display_client_id(api_key: str, fallback_id: int) -> str:
        alnum = "".join(ch for ch in api_key if ch.isalnum())
        if alnum:
            tail = alnum[-4:].upper().rjust(4, "X")
            return f"XXXXXX{tail}"
        return f"XXXXXX{str(fallback_id).zfill(4)[-4:]}"

    def connect_account(self, db: Session, user: User, payload: BrokerConnectRequest) -> BrokerAccountResponse:
        # Validate provided credentials up-front so UI can show a real connection error.
        selected_base_url: str | None = None
        try:
            candidate_client = get_broker_client(payload.broker_name, payload.api_key, payload.api_secret)
            candidate_client.get_balance()
        except Exception as exc:
            should_try_india = payload.broker_name == "delta" and self._extract_error_code(exc) == "invalid_api_key"

            if should_try_india:
                fallback_url = "https://api.india.delta.exchange"
                try:
                    candidate_client = get_broker_client(
                        payload.broker_name,
                        payload.api_key,
                        payload.api_secret,
                        base_url=fallback_url,
                    )
                    candidate_client.get_balance()
                    selected_base_url = fallback_url
                except Exception as fallback_exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=self._build_connect_error_message(fallback_exc),
                    ) from fallback_exc
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=self._build_connect_error_message(exc),
                ) from exc

        repo = BrokerRepository(db)
        account = repo.get_active_for_user(user.id, payload.broker_name)
        existing_metadata = self._parse_metadata(account.metadata_json) if account else {}
        metadata: dict[str, Any] = dict(existing_metadata)

        if payload.passphrase:
            metadata["passphrase"] = payload.passphrase
        else:
            metadata.pop("passphrase", None)

        if selected_base_url:
            metadata["base_url"] = selected_base_url

        if account is None:
            account = BrokerAccount(
                user_id=user.id,
                broker_name=payload.broker_name,
                api_key=encrypt_sensitive_value(payload.api_key),
                api_secret=encrypt_sensitive_value(payload.api_secret),
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            repo.create(account)
        else:
            account.api_key = encrypt_sensitive_value(payload.api_key)
            account.api_secret = encrypt_sensitive_value(payload.api_secret)
            account.metadata_json = json.dumps(metadata) if metadata else None

        db.commit()
        db.refresh(account)
        response = BrokerAccountResponse.model_validate(account)
        display_client_id = self._build_display_client_id(payload.api_key, account.id)
        return response.model_copy(update={"display_client_id": display_client_id})

    def get_active_client(self, db: Session, user: User, broker_name: str | None = None) -> BrokerClient:
        repo = BrokerRepository(db)
        account = repo.get_active_for_user(user.id, broker_name)
        if account:
            metadata = self._parse_metadata(account.metadata_json)
            return get_broker_client(
                account.broker_name,
                decrypt_sensitive_value(account.api_key),
                decrypt_sensitive_value(account.api_secret),
                base_url=metadata.get("base_url") if isinstance(metadata.get("base_url"), str) else None,
            )
        if broker_name:
            return get_broker_client(broker_name)
        return MockBroker()

    def list_connected_accounts(self, db: Session, user: User) -> list[BrokerAccountResponse]:
        repo = BrokerRepository(db)
        accounts = repo.list_active_for_user(user.id)
        responses: list[BrokerAccountResponse] = []
        for account in accounts:
            decrypted_key = decrypt_sensitive_value(account.api_key)
            display_client_id = self._build_display_client_id(decrypted_key, account.id)
            response = BrokerAccountResponse.model_validate(account).model_copy(
                update={"display_client_id": display_client_id}
            )
            responses.append(response)
        return responses

    def disconnect_account(self, db: Session, user: User, account_id: int) -> None:
        repo = BrokerRepository(db)
        account = repo.get_by_id_for_user(user.id, account_id)
        if account is None or not account.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")

        account.is_active = False
        db.commit()

    def place_order(
        self,
        db: Session,
        user: User,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal | None,
        order_type: str,
        broker_name: str,
    ) -> dict:
        client = self.get_active_client(db, user, broker_name)
        try:
            return client.place_order(symbol=symbol, side=side, quantity=quantity, price=price, order_type=order_type)
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_broker_exception(exc, "order placement")

    def get_balance(self, db: Session, user: User, broker_name: str | None = None) -> dict:
        client = self.get_active_client(db, user, broker_name)
        try:
            return client.get_balance()
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_broker_exception(exc, "balance fetch")

    def get_positions(self, db: Session, user: User, broker_name: str | None = None) -> list[dict]:
        client = self.get_active_client(db, user, broker_name)
        try:
            return client.get_positions()
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_broker_exception(exc, "positions fetch")

    def get_order_status(self, db: Session, user: User, order_id: str, broker_name: str | None = None) -> dict:
        client = self.get_active_client(db, user, broker_name)
        try:
            return client.get_order_status(order_id)
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_broker_exception(exc, "order status fetch")


broker_service = BrokerService()
