from contextlib import asynccontextmanager
import asyncio
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router_v1
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.core.rate_limit import limiter
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import *  # noqa: F401,F403
from app.models.user import User
from app.core.security import get_password_hash
from app.services.market_data_service import market_data_service
from app.services.websocket_manager import websocket_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    # For MVP we bootstrap schema at startup; migrations can be added in Phase 2.
    Base.metadata.create_all(bind=engine)
    _apply_schema_compatibility_patches()
    _seed_admin_account()
    logger.info("Database schema ensured")
    broadcaster = asyncio.create_task(_broadcast_market_data())
    yield
    broadcaster.cancel()


def _seed_admin_account() -> None:
    if not settings.admin_seed_email or not settings.admin_seed_password:
        return

    admin_email = settings.admin_seed_email.strip().lower()
    admin_name = settings.admin_seed_full_name.strip() or "Super Admin"

    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == admin_email).one_or_none()
        if admin_user is None:
            admin_user = User(
                email=admin_email,
                full_name=admin_name,
                hashed_password=get_password_hash(settings.admin_seed_password),
                role="admin",
                is_active=True,
            )
            db.add(admin_user)
        else:
            admin_user.full_name = admin_name
            admin_user.hashed_password = get_password_hash(settings.admin_seed_password)
            admin_user.role = "admin"
            admin_user.is_active = True
            db.add(admin_user)

        db.commit()
    finally:
        db.close()


def _apply_schema_compatibility_patches() -> None:
    # Backfill columns for users/trades created before the latest model updates.
    patches = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS trading_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_daily_loss NUMERIC(18,4) DEFAULT 500",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_trades_per_day INTEGER DEFAULT 50",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_level VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio VARCHAR(500)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS public_profile BOOLEAN DEFAULT TRUE",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
        "UPDATE users SET role = 'user' WHERE role IS NULL",
        "UPDATE users SET trading_enabled = TRUE WHERE trading_enabled IS NULL",
        "UPDATE users SET max_daily_loss = 500 WHERE max_daily_loss IS NULL",
        "UPDATE users SET max_trades_per_day = 50 WHERE max_trades_per_day IS NULL",
        "UPDATE users SET public_profile = TRUE WHERE public_profile IS NULL",
        "ALTER TABLE users ALTER COLUMN role SET NOT NULL",
        "ALTER TABLE users ALTER COLUMN trading_enabled SET NOT NULL",
        "ALTER TABLE users ALTER COLUMN max_daily_loss SET NOT NULL",
        "ALTER TABLE users ALTER COLUMN max_trades_per_day SET NOT NULL",
        "ALTER TABLE users ALTER COLUMN public_profile SET NOT NULL",
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_type VARCHAR(20) DEFAULT 'MARKET'",
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS broker VARCHAR(50) DEFAULT 'delta'",
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS leader_trade_id INTEGER",
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_loss NUMERIC(18,4)",
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS take_profit NUMERIC(18,4)",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS exchange VARCHAR(80) DEFAULT 'Delta Exchange'",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS followers INTEGER DEFAULT 0",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS recommended_margin NUMERIC(18,2) DEFAULT 1000",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS mdd_percent NUMERIC(7,2) DEFAULT 0",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS win_rate_percent NUMERIC(7,2) DEFAULT 0",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS pnl NUMERIC(18,2) DEFAULT 0",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS roi_percent NUMERIC(7,2) DEFAULT 0",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS chart_points TEXT",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS academy_slugs TEXT",
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS is_featured BOOLEAN DEFAULT FALSE",
        "UPDATE strategies SET exchange = 'Delta Exchange' WHERE exchange IS NULL",
        "UPDATE strategies SET followers = 0 WHERE followers IS NULL",
        "UPDATE strategies SET recommended_margin = 1000 WHERE recommended_margin IS NULL",
        "UPDATE strategies SET mdd_percent = 0 WHERE mdd_percent IS NULL",
        "UPDATE strategies SET win_rate_percent = 0 WHERE win_rate_percent IS NULL",
        "UPDATE strategies SET pnl = 0 WHERE pnl IS NULL",
        "UPDATE strategies SET roi_percent = 0 WHERE roi_percent IS NULL",
        "UPDATE strategies SET is_featured = FALSE WHERE is_featured IS NULL",
        "ALTER TABLE strategies ALTER COLUMN exchange SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN followers SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN recommended_margin SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN mdd_percent SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN win_rate_percent SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN pnl SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN roi_percent SET NOT NULL",
        "ALTER TABLE strategies ALTER COLUMN is_featured SET NOT NULL",
    ]

    with engine.begin() as connection:
        for statement in patches:
            connection.execute(text(statement))


async def _broadcast_market_data() -> None:
    symbols = ["BTCUSDT", "ETHUSDT", "AAPL", "NIFTY"]
    while True:
        for symbol in symbols:
            price = market_data_service.get_latest_price(symbol)
            await websocket_manager.broadcast({"type": "price_tick", "symbol": symbol, "price": str(price)})
        await asyncio.sleep(settings.market_data_poll_interval_seconds)


def create_app() -> FastAPI:
    configure_logging(settings.log_level)

    if settings.environment == "production":
        if "change-me" in settings.jwt_secret_key or "replace-with" in settings.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY must be a strong random secret in production")
        if "change-me" in settings.refresh_token_hash_secret or "replace-with" in settings.refresh_token_hash_secret:
            raise RuntimeError("REFRESH_TOKEN_HASH_SECRET must be a strong random secret in production")

    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}),
    )

    @app.middleware("http")
    async def normalize_double_slash_paths(request: Request, call_next):
        original_path = request.scope.get("path", "")
        if "//" in original_path:
            normalized = "/" + "/".join(part for part in original_path.split("/") if part)
            request.scope["path"] = normalized
            request.scope["raw_path"] = normalized.encode("utf-8")
        return await call_next(request)

    @app.middleware("http")
    async def harden_http(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id

        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > settings.max_request_size_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request payload too large"})

        started = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started) * 1000

        response.headers["X-Request-Id"] = request_id
        if settings.enable_security_headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
            response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
            if settings.environment == "production" and settings.hsts_max_age_seconds > 0:
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={settings.hsts_max_age_seconds}; includeSubDomains"
                )

        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(api_router_v1, prefix="/api/v1")

    @app.websocket("/ws/live")
    async def live_stream(websocket: WebSocket):
        await websocket_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await websocket_manager.disconnect(websocket)
        except Exception:
            await websocket_manager.disconnect(websocket)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
