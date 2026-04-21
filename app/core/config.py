from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "Algo Trading Platform"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    api_host: str
    api_port: int

    database_url: str
    redis_url: str

    celery_broker_url: str
    celery_result_backend: str
    websocket_heartbeat_seconds: int = 30
    market_data_poll_interval_seconds: int = 5

    jwt_secret_key: str = Field(default="change-me-in-prod", min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "algo-trading-api"
    jwt_audience: str = "algo-trading-clients"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_token_hash_secret: str = Field(
        default="change-me-refresh-secret-min-32-chars",
        min_length=32,
    )
    refresh_token_reuse_protection: bool = True
    max_active_sessions_per_user: int = Field(default=5, ge=1, le=20)
    login_lock_threshold: int = Field(default=5, ge=1, le=20)
    login_lock_duration_minutes: int = Field(default=15, ge=1, le=1440)
    otp_length: int = Field(default=6, ge=4, le=8)
    otp_expire_minutes: int = Field(default=10, ge=1, le=60)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_resend_cooldown_seconds: int = Field(default=30, ge=0, le=300)

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Algo Trading Platform"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    delta_api_key: str = ""
    delta_api_secret: str = ""
    delta_base_url: str
    delta_request_timeout_seconds: float = 15.0
    delta_symbol_type: str = "futures"
    broker_encryption_secret: str = Field(default="broker-encryption-secret-change-me", min_length=32)

    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    binance_api_key: str = ""
    binance_api_secret: str = ""

    rate_limit_default: str = "120/minute"
    rate_limit_use_forwarded_for: bool = True
    security_trusted_proxies: List[str] = []

    max_request_size_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    enable_security_headers: bool = True
    hsts_max_age_seconds: int = Field(default=31536000, ge=0)

    cors_origins: List[str]

    admin_seed_email: str = ""
    admin_seed_password: str = ""
    admin_seed_full_name: str = "Super Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
