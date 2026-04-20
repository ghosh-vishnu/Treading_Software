"""auth security hardening

Revision ID: 0002_auth_security_hardening
Revises: 0001_initial
Create Date: 2026-04-20 00:00:00.000000
"""

from alembic import op


revision = "0002_auth_security_hardening"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_revoked_at TIMESTAMP NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP NULL")

    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS device_name VARCHAR(120) NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS browser VARCHAR(80) NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS os VARCHAR(80) NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45) NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255) NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP NULL")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP NULL")

    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(80) NULL")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45) NULL")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255) NULL")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            id SERIAL PRIMARY KEY,
            jti VARCHAR(64) NOT NULL UNIQUE,
            user_id INTEGER NULL REFERENCES users(id),
            token_type VARCHAR(20) NOT NULL,
            reason VARCHAR(120) NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_revoked_tokens_jti ON revoked_tokens (jti)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_revoked_tokens_user_id ON revoked_tokens (user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL REFERENCES users(id),
            email VARCHAR(255) NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(255) NULL,
            is_success BOOLEAN NOT NULL DEFAULT FALSE,
            failure_reason VARCHAR(120) NULL,
            metadata_json TEXT NULL,
            attempted_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_attempts_user_id ON login_attempts (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_attempts_email ON login_attempts (email)")

    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id_revoked_at ON refresh_tokens (user_id, revoked_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_tokens_revoked_at ON users (tokens_revoked_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_locked_until ON users (locked_until)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS login_attempts")
    op.execute("DROP TABLE IF EXISTS revoked_tokens")

    op.execute("DROP INDEX IF EXISTS ix_refresh_tokens_user_id_revoked_at")
    op.execute("DROP INDEX IF EXISTS ix_users_tokens_revoked_at")
    op.execute("DROP INDEX IF EXISTS ix_users_locked_until")

    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS request_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS ip_address")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS user_agent")

    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS device_name")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS browser")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS os")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS ip_address")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS user_agent")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS revoked_at")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_attempts")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locked_until")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tokens_revoked_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at")