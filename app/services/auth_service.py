from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.login_attempt import LoginAttempt
from app.models.password_reset_token import PasswordResetToken
from app.models.password_history import PasswordHistory
from app.models.refresh_token import RefreshToken
from app.models.revoked_token import RevokedToken
from app.models.trusted_device import TrustedDevice
from app.models.user_profile import UserProfile
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionInfoResponse,
    TokenPair,
    TrustedDeviceResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserResponse,
)
from app.utils.storage import ALLOWED_AVATAR_CONTENT_TYPES, AVATAR_MAX_BYTES, save_avatar_bytes


class AuthService:
    def _get_or_create_profile(self, db: Session, user: User) -> UserProfile:
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        if profile is None:
            profile = UserProfile(user_id=user.id)
            db.add(profile)
            db.flush()
        return profile

    def _record_password_history(self, db: Session, user_id: int, password_hash: str) -> None:
        db.add(PasswordHistory(user_id=user_id, password_hash=password_hash))

    def _is_password_reused(self, db: Session, user_id: int, plain_password: str, *, limit: int = 5) -> bool:
        history_rows = list(
            db.scalars(
                select(PasswordHistory)
                .where(PasswordHistory.user_id == user_id)
                .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
                .limit(limit)
            ).all()
        )
        return any(verify_password(plain_password, row.password_hash) for row in history_rows)

    def _prune_password_history(self, db: Session, user_id: int, *, keep_last: int = 5) -> None:
        history_rows = list(
            db.scalars(
                select(PasswordHistory)
                .where(PasswordHistory.user_id == user_id)
                .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            ).all()
        )
        for stale_row in history_rows[keep_last:]:
            db.delete(stale_row)

    def _device_fingerprint(self, user_agent: str | None) -> str | None:
        if not user_agent:
            return None
        normalized = user_agent.strip().lower()
        if not normalized:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _merge_profile_response(self, user: User, profile: UserProfile | None) -> UserProfileResponse:
        mobile = profile.mobile if profile else user.phone
        return UserProfileResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            phone=user.phone,
            mobile=mobile,
            country=profile.country if profile else None,
            timezone=profile.timezone if profile else None,
            avatar_url=profile.avatar_url if profile else None,
            gender=user.gender,
            age=user.age,
            experience_level=user.experience_level,
            bio=user.bio,
            public_profile=user.public_profile,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    def _merge_user_response(self, user: User, profile: UserProfile | None) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            phone=user.phone,
            mobile=profile.mobile if profile else user.phone,
            country=profile.country if profile else None,
            timezone=profile.timezone if profile else None,
            avatar_url=profile.avatar_url if profile else None,
            gender=user.gender,
            age=user.age,
            experience_level=user.experience_level,
            bio=user.bio,
            public_profile=user.public_profile,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    def register(
        self,
        db: Session,
        payload: RegisterRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuthResponse:
        normalized_email = payload.email.lower().strip()
        existing = db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            email=normalized_email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            role="user",
            failed_login_attempts=0,
            locked_until=None,
            last_login_at=now,
            tokens_revoked_at=None,
            password_changed_at=now,
        )
        db.add(user)
        db.flush()
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        self._record_password_history(db, user.id, user.hashed_password)

        tokens = self._issue_tokens(db, user, ip_address=ip_address, user_agent=user_agent)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.signup",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self._record_login_attempt(
            db,
            user=user,
            email=user.email,
            success=True,
            failure_reason=None,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"source": "signup"},
        )
        db.commit()
        db.refresh(user)
        return AuthResponse(user=self._merge_user_response(user, profile), tokens=tokens)

    def login(
        self,
        db: Session,
        payload: LoginRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuthResponse:
        normalized_email = payload.email.lower().strip()
        user = db.scalar(select(User).where(User.email == normalized_email))
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if not user:
            self._record_login_attempt(
                db,
                user=None,
                email=normalized_email,
                success=False,
                failure_reason="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"source": "login"},
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not user.is_active or user.deleted_at is not None:
            self._record_login_attempt(
                db,
                user=user,
                email=user.email,
                success=False,
                failure_reason="inactive_account",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"source": "login"},
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

        if user.locked_until and user.locked_until > now:
            self._record_login_attempt(
                db,
                user=user,
                email=user.email,
                success=False,
                failure_reason="account_locked",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"locked_until": user.locked_until.isoformat()},
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is temporarily locked")

        if user.locked_until and user.locked_until <= now:
            user.locked_until = None
            user.failed_login_attempts = 0

        if not verify_password(payload.password, user.hashed_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            lock_triggered = user.failed_login_attempts >= settings.login_lock_threshold
            if lock_triggered:
                user.locked_until = now + timedelta(minutes=settings.login_lock_duration_minutes)

            self._record_login_attempt(
                db,
                user=user,
                email=user.email,
                success=False,
                failure_reason="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "attempts": user.failed_login_attempts,
                    "locked": lock_triggered,
                    "source": "login",
                },
            )
            self._write_audit(
                db,
                actor_user_id=user.id,
                action="auth.login_failed",
                target_type="user",
                target_id=str(user.id),
                metadata={"email": user.email, "reason": "invalid_credentials"},
                severity="warning",
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            db.add(user)
            db.commit()
            if lock_triggered:
                raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is temporarily locked")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        tokens = self._issue_tokens(db, user, ip_address=ip_address, user_agent=user_agent)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.login",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self._record_login_attempt(
            db,
            user=user,
            email=user.email,
            success=True,
            failure_reason=None,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"source": "login"},
        )
        db.commit()
        db.refresh(user)
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        return AuthResponse(user=self._merge_user_response(user, profile), tokens=tokens)

    def refresh_access_token(self, db: Session, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        token_record = self._find_refresh_token_record(db, refresh_token)
        user = db.scalar(select(User).where(User.id == int(user_id)))
        if not user or not user.is_active or user.deleted_at is not None:
            if token_record:
                token_record.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add(token_record)
                db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        if not token_record:
            if settings.refresh_token_reuse_protection:
                self._revoke_all_user_sessions(
                    db,
                    user,
                    reason="refresh_token_reuse",
                    revoke_access_tokens=True,
                )
                db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if token_record.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        if token_record.expires_at < now:
            token_record.revoked_at = now
            db.add(token_record)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
        if user.tokens_revoked_at and token_record.created_at < user.tokens_revoked_at:
            token_record.revoked_at = now
            db.add(token_record)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        token_record.revoked_at = now
        token_record.last_used_at = now
        db.add(token_record)

        tokens = self._issue_tokens(
            db,
            user,
            ip_address=token_record.ip_address,
            user_agent=token_record.user_agent,
        )
        db.commit()
        return tokens

    def revoke_refresh_token(
        self,
        db: Session,
        refresh_token: str,
        *,
        access_token: str | None = None,
        reason: str = "logout",
    ) -> None:
        token_record = self._find_refresh_token_record(db, refresh_token)
        if not token_record:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        token_record.revoked_at = now
        db.add(token_record)
        self._write_audit(
            db,
            actor_user_id=token_record.user_id,
            action="auth.logout",
            target_type="session",
            target_id=str(token_record.id),
            metadata={"user_id": token_record.user_id, "reason": reason},
            severity="info",
        )
        if access_token:
            self._revoke_access_token(db, access_token, token_record.user_id, reason=reason)
        db.commit()

    def logout_all_devices(
        self,
        db: Session,
        user: User,
        *,
        access_token: str | None = None,
        reason: str = "logout_all",
    ) -> None:
        self._revoke_all_user_sessions(db, user, reason=reason, revoke_access_tokens=True)
        if access_token:
            self._revoke_access_token(db, access_token, user.id, reason=reason)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.logout_all",
            target_type="user",
            target_id=str(user.id),
            metadata={"reason": reason},
            severity="warning",
        )
        db.commit()

    def forgot_password(
        self,
        db: Session,
        payload: ForgotPasswordRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> str | None:
        user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
        if not user or user.deleted_at is not None:
            return None

        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30),
            )
        )
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.forgot_password",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        return raw_token if settings.environment != "production" else None

    def reset_password(
        self,
        db: Session,
        payload: ResetPasswordRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
        reset_record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not reset_record or reset_record.is_used or reset_record.expires_at < now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        user = db.scalar(select(User).where(User.id == reset_record.user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if self._is_password_reused(db, user.id, payload.new_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password was used recently")

        user.hashed_password = get_password_hash(payload.new_password)
        user.password_changed_at = now
        user.tokens_revoked_at = now
        user.failed_login_attempts = 0
        user.locked_until = None
        reset_record.is_used = True
        self._revoke_all_user_sessions(db, user, reason="password_reset", revoke_access_tokens=False)
        self._record_password_history(db, user.id, user.hashed_password)
        self._prune_password_history(db, user.id)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.reset_password",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            severity="warning",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(user)
        db.add(reset_record)
        db.commit()

    def list_sessions(self, db: Session, user: User) -> list[SessionInfoResponse]:
        sessions = list(
            db.scalars(
                select(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                .order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
            ).all()
        )
        return [
            SessionInfoResponse(
                id=item.id,
                created_at=item.created_at,
                expires_at=item.expires_at,
                is_current=index == 0,
                is_trusted=item.is_trusted,
                device_name=item.device_name,
                browser=item.browser,
                os=item.os,
                ip_address=item.ip_address,
                user_agent=item.user_agent,
                last_used_at=item.last_used_at,
                revoked_at=item.revoked_at,
            )
            for index, item in enumerate(sessions)
        ]

    def revoke_session(self, db: Session, user: User, session_id: int) -> None:
        session = db.scalar(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.revoke_session",
            target_type="session",
            target_id=str(session.id),
            metadata={"session_id": session.id},
            severity="warning",
        )
        db.add(session)
        db.commit()

    def get_profile(self, db: Session, user: User) -> UserProfileResponse:
        profile = self._get_or_create_profile(db, user)
        return self._merge_profile_response(user, profile)

    def update_profile(
        self,
        db: Session,
        user: User,
        payload: UserProfileUpdateRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> UserProfileResponse:
        profile = self._get_or_create_profile(db, user)
        if payload.username:
            existing_by_username = db.scalar(select(User).where(User.username == payload.username, User.id != user.id))
            if existing_by_username:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already in use")

        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.username is not None:
            user.username = payload.username

        resolved_mobile = payload.mobile if payload.mobile is not None else payload.phone
        if resolved_mobile is not None:
            user.phone = resolved_mobile
            profile.mobile = resolved_mobile
        if payload.country is not None:
            profile.country = payload.country
        if payload.timezone is not None:
            profile.timezone = payload.timezone
        if payload.gender is not None:
            user.gender = payload.gender
        if payload.age is not None:
            user.age = payload.age
        if payload.experience_level is not None:
            user.experience_level = payload.experience_level
        if payload.bio is not None:
            user.bio = payload.bio
        if payload.public_profile is not None:
            user.public_profile = payload.public_profile

        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.update_profile",
            target_type="user",
            target_id=str(user.id),
            metadata={"fields": ["full_name", "username", "phone", "gender", "age", "experience_level", "bio", "public_profile"]},
            severity="info",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(user)
        db.add(profile)
        db.commit()
        db.refresh(user)
        db.refresh(profile)
        return self._merge_profile_response(user, profile)

    def change_password(
        self,
        db: Session,
        user: User,
        payload: ChangePasswordRequest,
        *,
        access_token: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            self._write_audit(
                db,
                actor_user_id=user.id,
                action="auth.change_password_failed",
                target_type="user",
                target_id=str(user.id),
                metadata={"email": user.email, "reason": "invalid_current_password"},
                severity="warning",
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        if verify_password(payload.new_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different")

        if self._is_password_reused(db, user.id, payload.new_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password was used recently")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user.hashed_password = get_password_hash(payload.new_password)
        user.password_changed_at = now
        user.tokens_revoked_at = now
        user.failed_login_attempts = 0
        user.locked_until = None
        self._revoke_all_user_sessions(db, user, reason="password_change", revoke_access_tokens=False)
        if access_token:
            self._revoke_access_token(db, access_token, user.id, reason="password_change")
        self._record_password_history(db, user.id, user.hashed_password)
        self._prune_password_history(db, user.id)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.change_password",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            severity="warning",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(user)
        db.commit()

    def delete_account(
        self,
        db: Session,
        user: User,
        payload: DeleteAccountRequest,
        *,
        access_token: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user.is_active = False
        user.deleted_at = now
        user.tokens_revoked_at = now
        user.failed_login_attempts = 0
        user.locked_until = None
        self._revoke_all_user_sessions(db, user, reason="account_deleted", revoke_access_tokens=False)
        trusted_devices = list(
            db.scalars(
                select(TrustedDevice).where(TrustedDevice.user_id == user.id, TrustedDevice.revoked_at.is_(None))
            ).all()
        )
        for device in trusted_devices:
            device.revoked_at = now
            db.add(device)
        if access_token:
            self._revoke_access_token(db, access_token, user.id, reason="account_deleted")
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.delete_account",
            target_type="user",
            target_id=str(user.id),
            metadata={"email": user.email},
            severity="warning",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(user)
        db.commit()

    def upload_avatar(
        self,
        db: Session,
        user: User,
        *,
        file_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> UserProfileResponse:
        if content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported avatar file type")
        if len(file_bytes) == 0 or len(file_bytes) > AVATAR_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar file is too large")

        profile = self._get_or_create_profile(db, user)
        avatar_url = save_avatar_bytes(user.id, file_bytes, file_name)
        profile.avatar_url = avatar_url
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.avatar_updated",
            target_type="user",
            target_id=str(user.id),
            metadata={"avatar_url": avatar_url},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return self._merge_profile_response(user, profile)

    def list_trusted_devices(self, db: Session, user: User) -> list[TrustedDeviceResponse]:
        devices = list(
            db.scalars(
                select(TrustedDevice)
                .where(TrustedDevice.user_id == user.id, TrustedDevice.revoked_at.is_(None))
                .order_by(TrustedDevice.trusted_at.desc(), TrustedDevice.id.desc())
            ).all()
        )
        return [TrustedDeviceResponse.model_validate(device) for device in devices]

    def trust_session(
        self,
        db: Session,
        user: User,
        session_id: int,
        *,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TrustedDeviceResponse:
        session = db.scalar(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        fingerprint = session.device_fingerprint or self._device_fingerprint(session.user_agent)
        if not fingerprint:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to identify device")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        trusted_device = db.scalar(
            select(TrustedDevice).where(
                TrustedDevice.user_id == user.id,
                TrustedDevice.device_fingerprint == fingerprint,
            )
        )
        if trusted_device is None:
            trusted_device = TrustedDevice(
                user_id=user.id,
                device_fingerprint=fingerprint,
                device_name=session.device_name,
                browser=session.browser,
                os=session.os,
                ip_address=ip_address or session.ip_address,
                user_agent=session.user_agent,
                trusted_at=now,
                last_seen_at=now,
            )
            db.add(trusted_device)
        else:
            trusted_device.revoked_at = None
            trusted_device.device_name = session.device_name
            trusted_device.browser = session.browser
            trusted_device.os = session.os
            trusted_device.ip_address = ip_address or session.ip_address
            trusted_device.user_agent = session.user_agent
            trusted_device.last_seen_at = now

        session.is_trusted = True
        db.add(session)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.trust_device",
            target_type="session",
            target_id=str(session.id),
            metadata={"fingerprint": fingerprint},
            severity="info",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()
        db.refresh(trusted_device)
        return TrustedDeviceResponse.model_validate(trusted_device)

    def revoke_trusted_device(
        self,
        db: Session,
        user: User,
        device_id: int,
        *,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        device = db.scalar(
            select(TrustedDevice).where(
                TrustedDevice.id == device_id,
                TrustedDevice.user_id == user.id,
                TrustedDevice.revoked_at.is_(None),
            )
        )
        if not device:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trusted device not found")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        device.revoked_at = now
        sessions = list(
            db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.device_fingerprint == device.device_fingerprint,
                    RefreshToken.revoked_at.is_(None),
                )
            ).all()
        )
        for session in sessions:
            session.is_trusted = False
            db.add(session)
        db.add(device)
        self._write_audit(
            db,
            actor_user_id=user.id,
            action="auth.revoke_trusted_device",
            target_type="trusted_device",
            target_id=str(device.id),
            metadata={"fingerprint": device.device_fingerprint},
            severity="warning",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.commit()

    def _issue_tokens(
        self,
        db: Session,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))

        device_name, browser, os_name = self._parse_user_agent(user_agent)
        device_fingerprint = self._device_fingerprint(user_agent)
        trusted_device = None
        if device_fingerprint:
            trusted_device = db.scalar(
                select(TrustedDevice).where(
                    TrustedDevice.user_id == user.id,
                    TrustedDevice.device_fingerprint == device_fingerprint,
                    TrustedDevice.revoked_at.is_(None),
                )
            )
        token_record = RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(refresh_token),
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            browser=browser,
            os=os_name,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            last_used_at=now,
            is_trusted=trusted_device is not None,
        )
        db.add(token_record)
        db.flush()

        if trusted_device is not None:
            trusted_device.last_seen_at = now
            trusted_device.device_name = device_name
            trusted_device.browser = browser
            trusted_device.os = os_name
            trusted_device.ip_address = ip_address
            trusted_device.user_agent = user_agent[:255] if user_agent else None
            db.add(trusted_device)

        active_sessions = list(
            db.scalars(
                select(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                .order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
            ).all()
        )
        for stale_record in active_sessions[settings.max_active_sessions_per_user :]:
            stale_record.revoked_at = now
            db.add(stale_record)

        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    def _find_refresh_token_record(self, db: Session, refresh_token: str) -> RefreshToken | None:
        token_hash = hash_refresh_token(refresh_token)
        return db.scalar(
            select(RefreshToken).where(
                RefreshToken.token == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        )

    def _revoke_all_user_sessions(
        self,
        db: Session,
        user: User,
        *,
        reason: str,
        revoke_access_tokens: bool,
    ) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user.tokens_revoked_at = now
        sessions = list(
            db.scalars(
                select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            ).all()
        )
        for session in sessions:
            session.revoked_at = now
            db.add(session)
        db.add(user)

        if revoke_access_tokens:
            self._write_audit(
                db,
                actor_user_id=user.id,
                action="auth.revoke_all_sessions",
                target_type="user",
                target_id=str(user.id),
                metadata={"reason": reason, "session_count": len(sessions)},
                severity="warning",
            )

    def _revoke_access_token(self, db: Session, access_token: str, user_id: int | None, *, reason: str) -> None:
        payload = decode_token(access_token)
        if not payload or payload.get("type") != "access":
            return

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return

        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
        existing = db.scalar(select(RevokedToken).where(RevokedToken.jti == str(jti)))
        if existing:
            return

        db.add(
            RevokedToken(
                jti=str(jti),
                user_id=user_id,
                token_type="access",
                reason=reason,
                expires_at=expires_at,
            )
        )

    def _record_login_attempt(
        self,
        db: Session,
        *,
        user: User | None,
        email: str | None,
        success: bool,
        failure_reason: str | None,
        ip_address: str | None,
        user_agent: str | None,
        metadata: dict | None = None,
    ) -> None:
        db.add(
            LoginAttempt(
                user_id=user.id if user else None,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent[:255] if user_agent else None,
                is_success=success,
                failure_reason=failure_reason,
                metadata_json=json.dumps(metadata or {}),
            )
        )

    def _parse_user_agent(self, user_agent: str | None) -> tuple[str | None, str | None, str | None]:
        if not user_agent:
            return None, None, None

        lowered = user_agent.lower()
        browser = "Unknown"
        if "edg/" in lowered or "edge/" in lowered:
            browser = "Edge"
        elif "chrome/" in lowered and "safari/" in lowered:
            browser = "Chrome"
        elif "firefox/" in lowered:
            browser = "Firefox"
        elif "safari/" in lowered:
            browser = "Safari"

        os_name = "Unknown"
        if "windows" in lowered:
            os_name = "Windows"
        elif "mac os" in lowered or "macintosh" in lowered:
            os_name = "macOS"
        elif "android" in lowered:
            os_name = "Android"
        elif "iphone" in lowered or "ipad" in lowered or "ios" in lowered:
            os_name = "iOS"
        elif "linux" in lowered:
            os_name = "Linux"

        device_name = "Mobile" if "mobile" in lowered or "android" in lowered or "iphone" in lowered else "Desktop"
        return device_name, browser, os_name

    def _write_audit(
        self,
        db: Session,
        actor_user_id: int | None,
        action: str,
        target_type: str,
        target_id: str | None,
        metadata: dict,
        severity: str = "info",
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        db.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                severity=severity,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent[:255] if user_agent else None,
                metadata_json=json.dumps(metadata),
            )
        )


auth_service = AuthService()
