"""add auth otp table

Revision ID: 0004_auth_otp_verification
Revises: 0003_user_profile_trusted_devices
Create Date: 2026-04-21 00:00:00.000001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_auth_otp_verification"
down_revision = "0003_user_profile_trusted_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "auth_otps" not in inspector.get_table_names():
        op.create_table(
            "auth_otps",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column("channel", sa.String(length=10), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=False),
            sa.Column("challenge_id", sa.String(length=80), nullable=False),
            sa.Column("otp_hash", sa.String(length=128), nullable=False),
            sa.Column("context_json", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspect(bind).get_indexes("auth_otps")}
    if "ix_auth_otps_user_id" not in existing_indexes:
        op.create_index("ix_auth_otps_user_id", "auth_otps", ["user_id"])
    if "ix_auth_otps_purpose" not in existing_indexes:
        op.create_index("ix_auth_otps_purpose", "auth_otps", ["purpose"])
    if "ix_auth_otps_channel" not in existing_indexes:
        op.create_index("ix_auth_otps_channel", "auth_otps", ["channel"])
    if "ix_auth_otps_recipient" not in existing_indexes:
        op.create_index("ix_auth_otps_recipient", "auth_otps", ["recipient"])
    if "ix_auth_otps_challenge_id" not in existing_indexes:
        op.create_index("ix_auth_otps_challenge_id", "auth_otps", ["challenge_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "auth_otps" not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("auth_otps")}
    if "ix_auth_otps_challenge_id" in existing_indexes:
        op.drop_index("ix_auth_otps_challenge_id", table_name="auth_otps")
    if "ix_auth_otps_recipient" in existing_indexes:
        op.drop_index("ix_auth_otps_recipient", table_name="auth_otps")
    if "ix_auth_otps_channel" in existing_indexes:
        op.drop_index("ix_auth_otps_channel", table_name="auth_otps")
    if "ix_auth_otps_purpose" in existing_indexes:
        op.drop_index("ix_auth_otps_purpose", table_name="auth_otps")
    if "ix_auth_otps_user_id" in existing_indexes:
        op.drop_index("ix_auth_otps_user_id", table_name="auth_otps")
    op.drop_table("auth_otps")
