# Backend - Algo Trading SaaS

FastAPI service for auth, broker integration, trade execution, strategy automation, copy trading, and realtime broadcasting.

## Local Run

1. Copy `.env.example` to `.env`.
2. Install dependencies.
3. Run migrations:

```bash
alembic upgrade head
```

4. Start API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Start Celery worker:

```bash
celery -A app.tasks.celery_app.celery_app worker -l info
```
