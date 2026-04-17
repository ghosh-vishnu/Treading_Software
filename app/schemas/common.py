from pydantic import BaseModel


class AdminDashboardSummary(BaseModel):
    total_customers: int
    active_customers: int
    total_admins: int
    total_strategies: int
    public_strategies: int
    total_academy_articles: int
    published_academy_articles: int
    total_trades: int
    open_trades: int


class MessageResponse(BaseModel):
    message: str
