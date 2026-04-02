from __future__ import annotations

import json
from decimal import Decimal

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
    def connect_account(self, db: Session, user: User, payload: BrokerConnectRequest) -> BrokerAccountResponse:
        repo = BrokerRepository(db)
        account = repo.get_active_for_user(user.id, payload.broker_name)
        metadata = {"passphrase": payload.passphrase} if payload.passphrase else {}

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
        return BrokerAccountResponse.model_validate(account)

    def get_active_client(self, db: Session, user: User, broker_name: str | None = None) -> BrokerClient:
        repo = BrokerRepository(db)
        account = repo.get_active_for_user(user.id, broker_name)
        if account:
            return get_broker_client(
                account.broker_name,
                decrypt_sensitive_value(account.api_key),
                decrypt_sensitive_value(account.api_secret),
            )
        if broker_name:
            return get_broker_client(broker_name)
        return MockBroker()

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
        return client.place_order(symbol=symbol, side=side, quantity=quantity, price=price, order_type=order_type)

    def get_balance(self, db: Session, user: User, broker_name: str | None = None) -> dict:
        client = self.get_active_client(db, user, broker_name)
        return client.get_balance()

    def get_positions(self, db: Session, user: User, broker_name: str | None = None) -> list[dict]:
        client = self.get_active_client(db, user, broker_name)
        return client.get_positions()

    def get_order_status(self, db: Session, user: User, order_id: str, broker_name: str | None = None) -> dict:
        client = self.get_active_client(db, user, broker_name)
        return client.get_order_status(order_id)


broker_service = BrokerService()
