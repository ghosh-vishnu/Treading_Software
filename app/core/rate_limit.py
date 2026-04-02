from slowapi import Limiter
from starlette.requests import Request

from app.core.config import settings


def _extract_client_ip(request: Request) -> str:
	direct_ip = request.client.host if request.client else "unknown"
	if not settings.rate_limit_use_forwarded_for:
		return direct_ip

	trusted_proxies = set(settings.security_trusted_proxies)
	if direct_ip not in trusted_proxies:
		return direct_ip

	forwarded_for = request.headers.get("x-forwarded-for", "")
	if not forwarded_for:
		return direct_ip

	first_hop = forwarded_for.split(",")[0].strip()
	return first_hop or direct_ip


def _rate_limit_key(request: Request) -> str:
	client_ip = _extract_client_ip(request)
	user_agent = request.headers.get("user-agent", "unknown")[:80]
	return f"{client_ip}:{user_agent}"


limiter = Limiter(
	key_func=_rate_limit_key,
	default_limits=[settings.rate_limit_default],
	headers_enabled=True,
)
