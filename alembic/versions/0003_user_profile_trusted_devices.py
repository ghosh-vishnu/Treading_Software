"""user profile, password history, and trusted devices

Revision ID: 0003_user_profile_trusted_devices
Revises: 0002_auth_security_hardening
Create Date: 2026-04-20 00:00:00.000001
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_user_profile_trusted_devices"
down_revision = "0002_auth_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    op.add_column("refresh_tokens", sa.Column("device_fingerprint", sa.String(length=128), nullable=True))
    op.add_column("refresh_tokens", sa.Column("is_trusted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_refresh_tokens_device_fingerprint", "refresh_tokens", ["device_fingerprint"])

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("mobile", sa.String(length=30), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_password_history_user_id", "password_history", ["user_id"])

    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("browser", sa.String(length=80), nullable=True),
        sa.Column("os", sa.String(length=80), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("trusted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "device_fingerprint", name="uq_trusted_devices_user_fingerprint"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index("ix_trusted_devices_device_fingerprint", "trusted_devices", ["device_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_trusted_devices_device_fingerprint", table_name="trusted_devices")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_constraint("uq_trusted_devices_user_fingerprint", "trusted_devices", type_="unique")
    op.drop_table("trusted_devices")

    op.drop_index("ix_password_history_user_id", table_name="password_history")
    op.drop_table("password_history")

    op.drop_table("user_profiles")

    op.drop_index("ix_refresh_tokens_device_fingerprint", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "is_trusted")
    op.drop_column("refresh_tokens", "device_fingerprint")

    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")