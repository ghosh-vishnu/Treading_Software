from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "algo_trading",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.trading"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
