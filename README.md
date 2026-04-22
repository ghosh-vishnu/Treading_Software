# Backend (FastAPI)

FastAPI service for auth, broker integration, trade execution, strategies, copy trading, admin endpoints, and realtime broadcasting.

## Setup (Windows / PowerShell)

```bash
cd backend
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: `http://localhost:8000/docs`  
Health: `http://localhost:8000/health`

## OTP auth (email + phone)

Signup:
- `POST /api/v1/auth/signup/send-otp`
- `POST /api/v1/auth/signup`

Login:
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/login/verify-otp`

Forgot/reset password:
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`

Note: In non-production environments, OTP responses can include debug fields (for local testing).

## Celery worker (optional)

Only required if you are using background tasks.

```bash
cd backend
.\.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app.celery_app worker -l info
```

## Production checklist (quick)
- Use `backend/.env.production.example` as baseline.
- Set strong values for `JWT_SECRET_KEY`, `REFRESH_TOKEN_HASH_SECRET`, `BROKER_ENCRYPTION_SECRET`.
- Configure SMTP/Twilio for OTP delivery.
- Run Alembic migrations (don’t rely on auto schema creation).
