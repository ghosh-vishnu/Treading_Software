import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import json
import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_admin
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.academy_article import AcademyArticle
from app.models.audit_log import AuditLog
from app.models.broker_account import BrokerAccount
from app.models.kyc_record import KYCRecord
from app.models.notification import Notification
from app.models.platform_setting import PlatformSetting
from app.models.strategy import Strategy
from app.models.subscription import Subscription
from app.models.trade import Trade
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.academy import AcademyArticleCreateRequest, AcademyArticleResponse, AcademyArticleUpdateRequest
from app.schemas.admin import (
    ActivityItem,
    AdminDashboardMetrics,
    AdminTradeItem,
    AdminTradeListResponse,
    AdminUserBanRequest,
    AdminUserItem,
    AdminUserListResponse,
    AuditLogListResponse,
    AuditLogResponse,
    BroadcastNotificationRequest,
    ChartPoint,
    ManualCloseTradeRequest,
    PagedMeta,
    PlatformSettingsResponse,
    PlatformSettingsUpdateRequest,
    StrategyBulkActionRequest,
    StrategyPerformanceResponse,
)
from app.schemas.common import AdminDashboardSummary, MessageResponse
from app.schemas.strategy import AdminStrategyCreateRequest, AdminStrategyUpdateRequest, StrategyResponse
from app.services.academy_service import academy_service
from app.services.admin_cache_service import admin_cache_service
from app.services.strategy_service import strategy_service
from app.services.websocket_manager import websocket_manager


router = APIRouter()

ADMIN_CACHE_PREFIX = "admin_cache:"
ADMIN_SUMMARY_TTL_SECONDS = 20
ADMIN_METRICS_TTL_SECONDS = 20
ADMIN_GROWTH_TTL_SECONDS = 30
ADMIN_ACTIVITIES_TTL_SECONDS = 10


def _write_audit(
    db: Session,
    actor_user_id: int,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict | None = None,
    severity: str = "info",
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            severity=severity,
            metadata_json=json.dumps(metadata or {}),
        )
    )


def _broadcast_payload(payload: dict) -> None:
    try:
        asyncio.run(websocket_manager.broadcast(payload))
    except RuntimeError:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(websocket_manager.broadcast(payload))


def _summary_cache_key() -> str:
    return f"{ADMIN_CACHE_PREFIX}summary"


def _metrics_cache_key() -> str:
    return f"{ADMIN_CACHE_PREFIX}metrics"


def _growth_cache_key(days: int) -> str:
    return f"{ADMIN_CACHE_PREFIX}growth:{days}"


def _activities_cache_key(limit: int) -> str:
    return f"{ADMIN_CACHE_PREFIX}activities:{limit}"


def _invalidate_admin_cache() -> None:
    admin_cache_service.delete_by_prefix(ADMIN_CACHE_PREFIX)


def _build_summary(db: Session) -> AdminDashboardSummary:
    total_customers = db.scalar(select(func.count()).select_from(User).where(User.role == "user")) or 0
    active_customers = db.scalar(select(func.count()).select_from(User).where(User.role == "user", User.is_active.is_(True))) or 0
    total_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    total_strategies = db.scalar(select(func.count()).select_from(Strategy)) or 0
    public_strategies = db.scalar(select(func.count()).select_from(Strategy).where(Strategy.is_public.is_(True))) or 0
    total_academy_articles = db.scalar(select(func.count()).select_from(AcademyArticle)) or 0
    published_academy_articles = db.scalar(select(func.count()).select_from(AcademyArticle).where(AcademyArticle.is_published.is_(True))) or 0
    total_trades = db.scalar(select(func.count()).select_from(Trade)) or 0
    open_trades = db.scalar(
        select(func.count()).select_from(Trade).where(Trade.status.in_(["PENDING", "OPEN", "PARTIALLY_FILLED"]))
    ) or 0

    return AdminDashboardSummary(
        total_customers=total_customers,
        active_customers=active_customers,
        total_admins=total_admins,
        total_strategies=total_strategies,
        public_strategies=public_strategies,
        total_academy_articles=total_academy_articles,
        published_academy_articles=published_academy_articles,
        total_trades=total_trades,
        open_trades=open_trades,
    )


def _build_metrics(db: Session) -> AdminDashboardMetrics:
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_traders = db.scalar(
        select(func.count()).select_from(User).where(User.trading_enabled.is_(True), User.is_active.is_(True))
    ) or 0
    total_strategies = db.scalar(select(func.count()).select_from(Strategy)) or 0
    trades_today = db.scalar(select(func.count()).select_from(Trade).where(Trade.created_at >= day_start)) or 0
    revenue = db.scalar(select(func.coalesce(func.sum(Trade.pnl), 0)).select_from(Trade).where(Trade.pnl > 0)) or Decimal("0")

    settings_row = db.scalar(select(PlatformSetting).order_by(PlatformSetting.id.asc()).limit(1))
    profit_share_percent = Decimal(str(settings_row.profit_share_percent if settings_row else 20.0))
    profit_share = (Decimal(str(revenue)) * (profit_share_percent / Decimal("100"))).quantize(Decimal("0.01"))

    total_followers = db.scalar(select(func.coalesce(func.sum(Strategy.followers), 0)).select_from(Strategy)) or 0
    total_subscriptions = db.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == "active")) or 0

    return AdminDashboardMetrics(
        total_users=total_users,
        active_traders=active_traders,
        total_strategies=total_strategies,
        trades_today=trades_today,
        revenue=Decimal(str(revenue)).quantize(Decimal("0.01")),
        profit_share=profit_share,
        total_followers=total_followers,
        total_subscriptions=total_subscriptions,
    )


def _build_growth(db: Session, days: int) -> list[ChartPoint]:
    start_date = datetime.utcnow() - timedelta(days=days - 1)

    rows = list(
        db.execute(
            select(func.date(Trade.created_at), func.count(Trade.id))
            .where(Trade.created_at >= start_date)
            .group_by(func.date(Trade.created_at))
            .order_by(func.date(Trade.created_at).asc())
        ).all()
    )
    row_map = {str(day): count for day, count in rows}

    points: list[ChartPoint] = []
    cursor = start_date
    while cursor.date() <= datetime.utcnow().date():
        key = str(cursor.date())
        points.append(ChartPoint(label=cursor.strftime("%d %b"), value=Decimal(str(row_map.get(key, 0)))))
        cursor += timedelta(days=1)
    return points


def _build_recent_activities(db: Session, limit: int) -> list[ActivityItem]:
    logs = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all())
    return [
        ActivityItem(
            id=f"audit-{item.id}",
            category=item.target_type,
            title=item.action,
            detail=item.metadata_json or "{}",
            created_at=item.created_at,
        )
        for item in logs
    ]


def _publish_admin_live_update(db: Session, event: str, actor_user_id: int, note: str) -> None:
    payload = {
        "type": "admin.live_update",
        "event": event,
        "actor_user_id": actor_user_id,
        "note": note,
        "summary": _build_summary(db).model_dump(mode="json"),
        "metrics": _build_metrics(db).model_dump(mode="json"),
        "activities": [item.model_dump(mode="json") for item in _build_recent_activities(db, 8)],
        "sent_at": datetime.utcnow().isoformat(),
    }
    _broadcast_payload(payload)


def _after_admin_mutation(db: Session, current_user: User, event: str, note: str) -> None:
    _invalidate_admin_cache()
    _publish_admin_live_update(db, event=event, actor_user_id=current_user.id, note=note)


@router.get("/summary", response_model=AdminDashboardSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user

    cached = admin_cache_service.get_json(_summary_cache_key())
    if cached is not None:
        return AdminDashboardSummary(**cached)

    fresh = _build_summary(db)
    admin_cache_service.set_json(_summary_cache_key(), fresh.model_dump(mode="json"), ADMIN_SUMMARY_TTL_SECONDS)
    return fresh


@router.get("/metrics", response_model=AdminDashboardMetrics)
def get_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user

    cached = admin_cache_service.get_json(_metrics_cache_key())
    if cached is not None:
        return AdminDashboardMetrics(**cached)

    fresh = _build_metrics(db)
    admin_cache_service.set_json(_metrics_cache_key(), fresh.model_dump(mode="json"), ADMIN_METRICS_TTL_SECONDS)
    return fresh


@router.get("/growth", response_model=list[ChartPoint])
def get_growth_chart(
    days: int = Query(default=14, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user

    key = _growth_cache_key(days)
    cached = admin_cache_service.get_json(key)
    if cached is not None:
        return [ChartPoint(**item) for item in cached]

    fresh = _build_growth(db, days)
    admin_cache_service.set_json(key, [item.model_dump(mode="json") for item in fresh], ADMIN_GROWTH_TTL_SECONDS)
    return fresh


@router.get("/activities", response_model=list[ActivityItem])
def get_recent_activities(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user

    key = _activities_cache_key(limit)
    cached = admin_cache_service.get_json(key)
    if cached is not None:
        return [ActivityItem(**item) for item in cached]

    fresh = _build_recent_activities(db, limit)
    admin_cache_service.set_json(key, [item.model_dump(mode="json") for item in fresh], ADMIN_ACTIVITIES_TTL_SECONDS)
    return fresh


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    kyc_status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    subscription_status: str | None = Query(default=None, pattern="^(active|inactive|cancelled)$"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|email|full_name)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    stmt = select(User).where(User.role == "user")

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern), User.username.ilike(pattern)))

    if sort_by == "email":
        order_col = User.email
    elif sort_by == "full_name":
        order_col = User.full_name
    else:
        order_col = User.created_at

    if sort_dir == "asc":
        stmt = stmt.order_by(order_col.asc())
    else:
        stmt = stmt.order_by(order_col.desc())

    users = list(db.scalars(stmt).all())
    items: list[AdminUserItem] = []
    for user in users:
        user_kyc = db.scalar(select(KYCRecord).where(KYCRecord.user_id == user.id))
        user_subscription = db.scalar(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.started_at.desc()).limit(1)
        )

        if kyc_status and (user_kyc.status if user_kyc else "pending") != kyc_status:
            continue
        if subscription_status and (user_subscription.status if user_subscription else "inactive") != subscription_status:
            continue

        linked_exchange_accounts = db.scalar(
            select(func.count())
            .select_from(BrokerAccount)
            .where(BrokerAccount.user_id == user.id, BrokerAccount.is_active.is_(True))
        ) or 0
        followers = db.scalar(select(func.coalesce(func.sum(Strategy.followers), 0)).where(Strategy.user_id == user.id)) or 0
        wallet = db.scalar(select(Wallet).where(Wallet.user_id == user.id))

        items.append(
            AdminUserItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                kyc_status=user_kyc.status if user_kyc else "pending",
                subscription_status=user_subscription.status if user_subscription else "inactive",
                linked_exchange_accounts=linked_exchange_accounts,
                followers=followers,
                wallet_balance=wallet.balance if wallet else Decimal("0"),
                created_at=user.created_at,
            )
        )

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return AdminUserListResponse(meta=PagedMeta(page=page, page_size=page_size, total=total), items=items[start:end])


@router.patch("/users/{user_id}/ban", response_model=MessageResponse)
@limiter.limit("30/minute")
def ban_or_unban_user(
    user_id: int,
    payload: AdminUserBanRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    user = db.scalar(select(User).where(User.id == user_id, User.role == "user"))
    if not user:
        return MessageResponse(message="User not found")

    user.is_active = payload.is_active
    db.add(user)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="user.unban" if payload.is_active else "user.ban",
        target_type="user",
        target_id=str(user.id),
        metadata={"email": user.email, "is_active": user.is_active},
        severity="warning",
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="user.status_changed", note=f"User {user.id} status updated")
    return MessageResponse(message="User status updated")


@router.get("/trades", response_model=AdminTradeListResponse)
def list_trades(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None),
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    stmt = select(Trade)

    conditions = []
    if status_filter:
        conditions.append(Trade.status == status_filter)
    if search:
        pattern = f"%{search.strip().upper()}%"
        conditions.append(or_(Trade.symbol.ilike(pattern), Trade.strategy_tag.ilike(pattern)))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    items = list(db.scalars(stmt.order_by(Trade.created_at.desc())).all())
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = [AdminTradeItem.model_validate(item) for item in items[start:end]]
    return AdminTradeListResponse(meta=PagedMeta(page=page, page_size=page_size, total=total), items=page_items)


@router.post("/trades/{trade_id}/manual-close", response_model=MessageResponse)
@limiter.limit("30/minute")
def manual_close_trade(
    trade_id: int,
    payload: ManualCloseTradeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    trade = db.scalar(select(Trade).where(Trade.id == trade_id))
    if not trade:
        return MessageResponse(message="Trade not found")

    if trade.status in {"CLOSED", "CANCELLED"}:
        return MessageResponse(message="Trade is already closed")

    if trade.side == "BUY":
        pnl = (payload.close_price - Decimal(str(trade.price))) * Decimal(str(trade.quantity))
    else:
        pnl = (Decimal(str(trade.price)) - payload.close_price) * Decimal(str(trade.quantity))

    trade.status = "CLOSED"
    trade.pnl = pnl.quantize(Decimal("0.0001"))
    db.add(trade)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="trade.manual_close",
        target_type="trade",
        target_id=str(trade.id),
        metadata={"close_price": str(payload.close_price), "pnl": str(trade.pnl)},
        severity="warning",
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="trade.closed", note=f"Trade {trade.id} manually closed")
    return MessageResponse(message="Trade closed manually")


@router.post("/trades/sync", response_model=MessageResponse)
@limiter.limit("10/minute")
def sync_trades(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="trade.sync_requested",
        target_type="trade",
        target_id=None,
        metadata={"source": "admin"},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="trade.sync_requested", note="Trade sync requested")
    return MessageResponse(message="Trade sync queued")


@router.get("/strategies", response_model=list[StrategyResponse])
def list_all_strategies(
    search: str | None = None,
    risk_level: str | None = Query(default=None, pattern="^(low|medium|high)$"),
    is_public: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    stmt = select(Strategy)

    conditions = []
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(or_(Strategy.name.ilike(pattern), Strategy.strategy_tag.ilike(pattern), Strategy.exchange.ilike(pattern)))
    if risk_level:
        conditions.append(Strategy.risk_level == risk_level)
    if is_public is not None:
        conditions.append(Strategy.is_public.is_(is_public))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    strategies = list(db.scalars(stmt.order_by(Strategy.created_at.desc())).all())
    return [StrategyResponse.model_validate(item) for item in strategies]


@router.post("/strategies", response_model=StrategyResponse)
@limiter.limit("20/minute")
def create_strategy(
    request: Request,
    response: Response,
    payload: AdminStrategyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    strategy = strategy_service.create_admin_strategy(db, current_user, payload)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="strategy.create",
        target_type="strategy",
        target_id=str(strategy.id),
        metadata={"strategy_tag": strategy.strategy_tag},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="strategy.created", note=f"Strategy {strategy.id} created")
    return strategy


@router.patch("/strategies/{strategy_id}", response_model=StrategyResponse)
@limiter.limit("30/minute")
def update_strategy(
    strategy_id: int,
    request: Request,
    response: Response,
    payload: AdminStrategyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    strategy = strategy_service.update_admin_strategy(db, strategy_id, payload)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="strategy.update",
        target_type="strategy",
        target_id=str(strategy.id),
        metadata={"strategy_tag": strategy.strategy_tag},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="strategy.updated", note=f"Strategy {strategy.id} updated")
    return strategy


@router.delete("/strategies/{strategy_id}", response_model=MessageResponse)
@limiter.limit("30/minute")
def delete_strategy(
    strategy_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    strategy_service.delete_admin_strategy(db, strategy_id)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="strategy.delete",
        target_type="strategy",
        target_id=str(strategy_id),
        severity="warning",
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="strategy.deleted", note=f"Strategy {strategy_id} deleted")
    return MessageResponse(message="Strategy deleted")


@router.post("/strategies/bulk", response_model=MessageResponse)
@limiter.limit("20/minute")
def bulk_strategy_action(
    payload: StrategyBulkActionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    strategies = list(db.scalars(select(Strategy).where(Strategy.id.in_(payload.strategy_ids))).all())
    if not strategies:
        return MessageResponse(message="No strategies found for selected IDs")

    for strategy in strategies:
        if payload.action == "publish":
            strategy.is_public = True
        elif payload.action == "unpublish":
            strategy.is_public = False
        elif payload.action == "feature":
            strategy.is_featured = True
        elif payload.action == "unfeature":
            strategy.is_featured = False
        elif payload.action == "delete":
            db.delete(strategy)
        elif payload.action == "duplicate":
            duplicate = Strategy(
                name=f"{strategy.name} Copy",
                description=strategy.description,
                user_id=current_user.id,
                strategy_tag=f"{strategy.strategy_tag}-copy-{secrets.token_hex(3)}",
                is_public=False,
                exchange=strategy.exchange,
                risk_level=strategy.risk_level,
                logo_url=strategy.logo_url,
                image_url=strategy.image_url,
                tags=strategy.tags,
                followers=0,
                recommended_margin=strategy.recommended_margin,
                mdd_percent=strategy.mdd_percent,
                win_rate_percent=strategy.win_rate_percent,
                pnl=Decimal("0"),
                roi_percent=Decimal("0"),
                chart_points=strategy.chart_points,
                academy_slugs=strategy.academy_slugs,
                is_featured=False,
            )
            db.add(duplicate)

    _write_audit(
        db,
        actor_user_id=current_user.id,
        action=f"strategy.bulk_{payload.action}",
        target_type="strategy",
        target_id=",".join(str(item) for item in payload.strategy_ids),
        metadata={"count": len(payload.strategy_ids)},
        severity="warning" if payload.action in {"delete"} else "info",
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="strategy.bulk_action", note=f"Bulk action: {payload.action}")
    return MessageResponse(message=f"Bulk action completed: {payload.action}")


@router.get("/strategies/{strategy_id}/performance", response_model=StrategyPerformanceResponse)
def strategy_performance(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    strategy = db.scalar(select(Strategy).where(Strategy.id == strategy_id))
    if not strategy:
        return StrategyPerformanceResponse(
            equity_curve=[],
            daily_returns=[],
            monthly_returns=[],
            drawdown_curve=[],
            win_loss_ratio=Decimal("0"),
            average_rr=Decimal("0"),
            open_positions=0,
        )

    chart_values = [Decimal(item) for item in (strategy.chart_points or "").split(",") if item.strip()]
    if not chart_values:
        chart_values = [Decimal("0")]

    equity_curve = [ChartPoint(label=f"P{i + 1}", value=value) for i, value in enumerate(chart_values)]

    daily_returns: list[ChartPoint] = []
    for index, value in enumerate(chart_values[-7:]):
        daily_returns.append(ChartPoint(label=f"D{index + 1}", value=value))

    monthly_returns: list[ChartPoint] = []
    for index in range(min(6, len(chart_values))):
        monthly_returns.append(ChartPoint(label=f"M{index + 1}", value=chart_values[index]))

    peak = chart_values[0]
    drawdown_curve: list[ChartPoint] = []
    for index, value in enumerate(chart_values):
        if value > peak:
            peak = value
        dd = ((peak - value) / peak * Decimal("100")) if peak > 0 else Decimal("0")
        drawdown_curve.append(ChartPoint(label=f"P{index + 1}", value=dd.quantize(Decimal("0.01"))))

    trades = list(db.scalars(select(Trade).where(Trade.strategy_tag == strategy.strategy_tag)).all())
    wins = len([trade for trade in trades if trade.pnl > 0])
    losses = len([trade for trade in trades if trade.pnl <= 0])
    win_loss_ratio = Decimal(str(wins / losses)).quantize(Decimal("0.01")) if losses else Decimal(str(wins))

    avg_win = (sum((trade.pnl for trade in trades if trade.pnl > 0), Decimal("0")) / wins) if wins else Decimal("0")
    avg_loss = (sum((abs(trade.pnl) for trade in trades if trade.pnl < 0), Decimal("0")) / losses) if losses else Decimal("1")
    average_rr = (avg_win / avg_loss).quantize(Decimal("0.01")) if avg_loss > 0 else Decimal("0")

    open_positions = len([trade for trade in trades if trade.status in {"OPEN", "PENDING", "PARTIALLY_FILLED"}])

    return StrategyPerformanceResponse(
        equity_curve=equity_curve,
        daily_returns=daily_returns,
        monthly_returns=monthly_returns,
        drawdown_curve=drawdown_curve,
        win_loss_ratio=win_loss_ratio,
        average_rr=average_rr,
        open_positions=open_positions,
    )


@router.get("/academy/articles", response_model=list[AcademyArticleResponse])
def list_all_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    return academy_service.list_all_articles(db)


@router.post("/academy/articles", response_model=AcademyArticleResponse)
@limiter.limit("20/minute")
def create_article(
    request: Request,
    response: Response,
    payload: AcademyArticleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    article = academy_service.create_article(db, payload)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="academy.create",
        target_type="academy_article",
        target_id=str(article.id),
        metadata={"slug": article.slug},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="academy.created", note=f"Article {article.id} created")
    return article


@router.patch("/academy/articles/{article_id}", response_model=AcademyArticleResponse)
@limiter.limit("30/minute")
def update_article(
    article_id: int,
    request: Request,
    response: Response,
    payload: AcademyArticleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    article = academy_service.update_article(db, article_id, payload)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="academy.update",
        target_type="academy_article",
        target_id=str(article.id),
        metadata={"slug": article.slug},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="academy.updated", note=f"Article {article.id} updated")
    return article


@router.delete("/academy/articles/{article_id}", response_model=MessageResponse)
@limiter.limit("30/minute")
def delete_article(
    article_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    academy_service.delete_article(db, article_id)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="academy.delete",
        target_type="academy_article",
        target_id=str(article_id),
        severity="warning",
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="academy.deleted", note=f"Article {article_id} deleted")
    return MessageResponse(message="Article deleted")


@router.post("/notifications/broadcast", response_model=MessageResponse)
@limiter.limit("10/minute")
def broadcast_notification(
    payload: BroadcastNotificationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    users = list(db.scalars(select(User).where(User.is_active.is_(True))).all())
    for user in users:
        db.add(
            Notification(
                user_id=user.id,
                category=payload.category,
                title=payload.title,
                message=payload.message,
            )
        )

    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="notification.broadcast",
        target_type="notification",
        target_id=None,
        metadata={"count": len(users), "category": payload.category},
    )
    db.commit()
    _after_admin_mutation(db, current_user, event="notification.broadcast", note=f"Broadcast to {len(users)} users")
    return MessageResponse(message=f"Notification sent to {len(users)} users")


@router.get("/platform-settings", response_model=PlatformSettingsResponse)
def get_platform_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    row = db.scalar(select(PlatformSetting).order_by(PlatformSetting.id.asc()).limit(1))
    if not row:
        row = PlatformSetting()
        db.add(row)
        db.commit()
        db.refresh(row)
    return PlatformSettingsResponse.model_validate(row)


@router.patch("/platform-settings", response_model=PlatformSettingsResponse)
@limiter.limit("20/minute")
def update_platform_settings(
    payload: PlatformSettingsUpdateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = (request, response)
    row = db.scalar(select(PlatformSetting).order_by(PlatformSetting.id.asc()).limit(1))
    if not row:
        row = PlatformSetting()
        db.add(row)
        db.flush()

    updates = payload.model_dump()
    for field_name, value in updates.items():
        setattr(row, field_name, value)

    db.add(row)
    _write_audit(
        db,
        actor_user_id=current_user.id,
        action="settings.update",
        target_type="platform_settings",
        target_id=str(row.id),
        metadata={"maintenance_mode": row.maintenance_mode},
        severity="warning" if row.maintenance_mode else "info",
    )
    db.commit()
    db.refresh(row)
    _after_admin_mutation(db, current_user, event="settings.updated", note="Platform settings updated")
    return PlatformSettingsResponse.model_validate(row)


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    severity: str | None = Query(default=None, pattern="^(info|warning|error)$"),
    action: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _ = current_user
    stmt = select(AuditLog)
    if severity:
        stmt = stmt.where(AuditLog.severity == severity)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))

    all_items = list(db.scalars(stmt.order_by(AuditLog.created_at.desc())).all())
    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    items = [AuditLogResponse.model_validate(item) for item in all_items[start:end]]
    return AuditLogListResponse(meta=PagedMeta(page=page, page_size=page_size, total=total), items=items)
