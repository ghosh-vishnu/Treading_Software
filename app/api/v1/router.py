from fastapi import APIRouter

from app.api.v1.routes import auth, broker, copy, dashboard, strategy, trade


api_router_v1 = APIRouter()
api_router_v1.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router_v1.include_router(trade.router, prefix="/trades", tags=["trades"])
api_router_v1.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router_v1.include_router(strategy.router, prefix="/strategy", tags=["strategy"])
api_router_v1.include_router(broker.router, prefix="/broker", tags=["broker"])
api_router_v1.include_router(copy.router, prefix="/copy", tags=["copy-trading"])
