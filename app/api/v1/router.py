from fastapi import APIRouter

from app.api.v1.routes import academy, auth, backtesting, broker, copy, dashboard, kyc, notifications, settings, strategy, trade


api_router_v1 = APIRouter()
api_router_v1.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router_v1.include_router(trade.router, prefix="/trades", tags=["trades"])
api_router_v1.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router_v1.include_router(strategy.router, prefix="/strategy", tags=["strategy"])
api_router_v1.include_router(broker.router, prefix="/broker", tags=["broker"])
api_router_v1.include_router(copy.router, prefix="/copy", tags=["copy-trading"])
api_router_v1.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router_v1.include_router(kyc.router, prefix="/kyc", tags=["kyc"])
api_router_v1.include_router(academy.router, prefix="/academy", tags=["academy"])
api_router_v1.include_router(backtesting.router, prefix="/backtesting", tags=["backtesting"])
api_router_v1.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
