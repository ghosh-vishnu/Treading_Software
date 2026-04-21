# Backend - Algo Trading SaaS

FastAPI service for auth, broker integration, trade execution, strategy automation, copy trading, and realtime broadcasting.

## OTP Auth Setup

Signup and login are OTP-based.

1. Configure SMTP for email OTP in `.env`:
	- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
	- `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS`, `SMTP_USE_SSL`
2. Configure Twilio for phone OTP in `.env`:
	- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
3. Optional OTP controls:
	- `OTP_LENGTH`, `OTP_EXPIRE_MINUTES`, `OTP_MAX_ATTEMPTS`

Auth flow:
- Signup: `/api/v1/auth/signup/send-otp` -> `/api/v1/auth/signup/verify-otp` -> `/api/v1/auth/signup`
- Login: `/api/v1/auth/login` or `/api/v1/auth/login/send-otp` -> `/api/v1/auth/login/verify-otp`

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
