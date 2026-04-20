from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet

from app.core.config import settings


# Use PBKDF2-SHA256 for stable cross-platform hashing behavior.
# This avoids known runtime issues with specific passlib+bcrypt combinations.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=390000,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def hash_refresh_token(token: str) -> str:
    digest = hmac.new(
        settings.refresh_token_hash_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _fernet() -> Fernet:
    key_material = hashlib.sha256(settings.broker_encryption_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_sensitive_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_sensitive_value(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    issued_at = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": issued_at,
        "nbf": issued_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": secrets.token_urlsafe(24),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject=subject,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require_sub": True,
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
                "require_jti": True,
            },
        )
    except JWTError:
        return None


def get_token_jti(token: str) -> Optional[str]:
    payload = decode_token(token)
    if not payload:
        return None
    jti = payload.get("jti")
    return str(jti) if jti is not None else None


def get_token_issued_at(token: str) -> Optional[datetime]:
    payload = decode_token(token)
    if not payload:
        return None
    issued_at = payload.get("iat")
    if isinstance(issued_at, datetime):
        return issued_at.astimezone(timezone.utc)
    if isinstance(issued_at, (int, float)):
        return datetime.fromtimestamp(issued_at, tz=timezone.utc)
    return None


def is_token_expired(token: str) -> bool:
    payload = decode_token(token)
    if not payload:
        return True
    exp = payload.get("exp")
    if not exp:
        return True
    return datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc)

