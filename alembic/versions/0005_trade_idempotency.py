"""add trade idempotency key

Revision ID: 0005_trade_idempotency
Revises: 0004_auth_otp_verification
Create Date: 2026-04-24 00:00:00.000001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0005_trade_idempotency"
down_revision = "0004_auth_otp_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("trades")}
    if "idempotency_key" not in columns:
        op.add_column("trades", sa.Column("idempotency_key", sa.String(length=80), nullable=True))

    existing_indexes = {idx["name"] for idx in inspect(bind).get_indexes("trades")}
    if "ix_trades_user_broker_idempotency" not in existing_indexes:
        op.create_index(
            "ix_trades_user_broker_idempotency",
            "trades",
            ["user_id", "broker", "idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("trades")}
    if "ix_trades_user_broker_idempotency" in existing_indexes:
        op.drop_index("ix_trades_user_broker_idempotency", table_name="trades")

    columns = {column["name"] for column in inspector.get_columns("trades")}
    if "idempotency_key" in columns:
        op.drop_column("trades", "idempotency_key")
