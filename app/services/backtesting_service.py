from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.backtest_run import BacktestRun
from app.models.user import User
from app.schemas.backtesting import BacktestRunRequest, BacktestRunResponse


class BacktestingService:
    def run(self, db: Session, user: User, payload: BacktestRunRequest) -> BacktestRunResponse:
        seed = int(hashlib.sha256(f"{payload.symbol}:{payload.strategy_tag}".encode("utf-8")).hexdigest()[:8], 16)
        wins = 0
        losses = 0
        equity = Decimal(str(payload.initial_capital))
        peak = equity
        max_drawdown = Decimal("0")
        equity_curve: list[float] = [float(equity)]

        for i in range(payload.periods):
            direction = 1 if ((seed + i * 17) % 100) > 45 else -1
            move = Decimal(((seed + i * 13) % 35)) / Decimal("1000")
            pnl_change = equity * move * Decimal(direction)
            equity += pnl_change
            if pnl_change >= 0:
                wins += 1
            else:
                losses += 1
            peak = max(peak, equity)
            drawdown = ((peak - equity) / peak * Decimal("100")) if peak > 0 else Decimal("0")
            max_drawdown = max(max_drawdown, drawdown)
            equity_curve.append(float(equity))

        roi = ((equity - Decimal(str(payload.initial_capital))) / Decimal(str(payload.initial_capital)) * Decimal("100"))
        total = wins + losses
        win_rate = (Decimal(wins) / Decimal(total) * Decimal("100")) if total else Decimal("0")

        report = {
            "initial_capital": payload.initial_capital,
            "final_capital": float(equity),
            "equity_curve": equity_curve,
            "wins": wins,
            "losses": losses,
        }

        run = BacktestRun(
            user_id=user.id,
            strategy_tag=payload.strategy_tag,
            symbol=payload.symbol.upper(),
            timeframe=payload.timeframe,
            periods=payload.periods,
            roi=float(roi.quantize(Decimal("0.0001"))),
            drawdown=float(max_drawdown.quantize(Decimal("0.0001"))),
            win_rate=float(win_rate.quantize(Decimal("0.0001"))),
            report_json=json.dumps(report),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return BacktestRunResponse.model_validate(run)


backtesting_service = BacktestingService()
