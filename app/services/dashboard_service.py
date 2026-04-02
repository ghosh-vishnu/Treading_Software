from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.user import User
from app.repositories.trade_repository import TradeRepository
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardOpenPosition,
    DashboardPnLSummary,
    DashboardStrategyPerformance,
    DashboardSummaryResponse,
)
from app.services.broker_service import broker_service


class DashboardService:
    def get_summary(self, db: Session, user: User) -> DashboardSummaryResponse:
        base_query = select(
            func.count(Trade.id),
            func.coalesce(func.sum(Trade.pnl), Decimal("0")),
            func.sum(case((Trade.pnl > 0, 1), else_=0)),
            func.sum(case((Trade.pnl < 0, 1), else_=0)),
        ).where(Trade.user_id == user.id)

        total, pnl, winners, losers = db.execute(base_query).one()

        return DashboardSummaryResponse(
            total_trades=total or 0,
            cumulative_pnl=pnl or Decimal("0"),
            winning_trades=winners or 0,
            losing_trades=losers or 0,
        )

    def get_overview(self, db: Session, user: User) -> DashboardOverviewResponse:
        trade_repo = TradeRepository(db)
        now = datetime.utcnow()
        start_of_day = datetime(now.year, now.month, now.day)
        start_of_week = start_of_day - timedelta(days=now.weekday())

        daily = Decimal(str(trade_repo.sum_pnl_for_user_since(user.id, start_of_day)))
        weekly = Decimal(str(trade_repo.sum_pnl_for_user_since(user.id, start_of_week)))
        total = self.get_summary(db, user).cumulative_pnl
        summary = self.get_summary(db, user)
        win_rate = Decimal("0")
        if summary.total_trades:
            win_rate = (Decimal(summary.winning_trades) / Decimal(summary.total_trades) * Decimal("100")).quantize(Decimal("0.01"))

        open_positions_raw = broker_service.get_positions(db, user)
        open_positions = [
            DashboardOpenPosition(
                symbol=str(position.get("symbol", "")),
                quantity=Decimal(str(position.get("quantity", 0))),
                avg_entry_price=Decimal(str(position.get("avg_entry_price", position.get("entry_price", 0)))),
                unrealized_pnl=Decimal(str(position.get("unrealized_pnl", 0))),
            )
            for position in open_positions_raw
        ]

        strategy_stats: dict[str, dict[str, Decimal | int]] = {}
        for trade in trade_repo.list_for_user(user.id):
            key = trade.strategy_tag or "manual"
            bucket = strategy_stats.setdefault(key, {"trades": 0, "wins": 0, "pnl": Decimal("0")})
            bucket["trades"] = int(bucket["trades"]) + 1
            bucket["pnl"] = Decimal(str(bucket["pnl"])) + Decimal(str(trade.pnl))
            if Decimal(str(trade.pnl)) > 0:
                bucket["wins"] = int(bucket["wins"]) + 1

        strategy_performance = [
            DashboardStrategyPerformance(
                strategy_tag=strategy_tag,
                total_trades=int(stats["trades"]),
                win_rate=(Decimal(stats["wins"]) / Decimal(stats["trades"]) * Decimal("100")).quantize(Decimal("0.01")) if stats["trades"] else Decimal("0"),
                pnl=Decimal(str(stats["pnl"])),
            )
            for strategy_tag, stats in strategy_stats.items()
        ]

        return DashboardOverviewResponse(
            pnl=DashboardPnLSummary(daily=daily, weekly=weekly, total=total),
            win_rate=win_rate,
            trade_history_count=summary.total_trades,
            open_positions=open_positions,
            strategy_performance=strategy_performance,
            updated_at=now,
        )


dashboard_service = DashboardService()
