from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
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
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenPair,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserResponse,
)


class AuthService:
    def register(self, db: Session, payload: RegisterRequest) -> AuthResponse:
        normalized_email = payload.email.lower()
        existing = db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = User(
            email=normalized_email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            role=payload.role,
        )
        db.add(user)
        db.flush()

        tokens = self._issue_tokens(db, user)
        db.commit()
        db.refresh(user)
        return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)

    def login(self, db: Session, payload: LoginRequest) -> AuthResponse:
        user = db.scalar(select(User).where(User.email == payload.email.lower()))
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

        tokens = self._issue_tokens(db, user)
        db.commit()
        return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)

    def refresh_access_token(self, db: Session, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        token_record = self._find_refresh_token_record(db, refresh_token)
        if not token_record:
            # Possible replay of an already-rotated token. Optionally revoke all sessions for the user.
            if settings.refresh_token_reuse_protection:
                db.query(RefreshToken).filter(RefreshToken.user_id == int(user_id)).delete(synchronize_session=False)
                db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        if token_record.user_id != int(user_id):
            db.delete(token_record)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        if token_record.expires_at < datetime.utcnow():
            db.delete(token_record)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        user = db.scalar(select(User).where(User.id == int(user_id)))
        if not user or not user.is_active:
            db.delete(token_record)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        db.delete(token_record)
        tokens = self._issue_tokens(db, user)
        db.commit()
        return tokens

    def revoke_refresh_token(self, db: Session, refresh_token: str) -> None:
        token_record = self._find_refresh_token_record(db, refresh_token)
        if token_record:
            db.delete(token_record)
            db.commit()

    def get_profile(self, user: User) -> UserProfileResponse:
        return UserProfileResponse.model_validate(user)

    def update_profile(self, db: Session, user: User, payload: UserProfileUpdateRequest) -> UserProfileResponse:
        if payload.username:
            existing_by_username = db.scalar(select(User).where(User.username == payload.username, User.id != user.id))
            if existing_by_username:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already in use")

        user.full_name = payload.full_name
        user.username = payload.username
        user.phone = payload.phone
        user.gender = payload.gender
        user.age = payload.age
        user.experience_level = payload.experience_level
        user.bio = payload.bio
        user.public_profile = payload.public_profile

        db.add(user)
        db.commit()
        db.refresh(user)
        return UserProfileResponse.model_validate(user)

    def change_password(self, db: Session, user: User, payload: ChangePasswordRequest) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        if payload.current_password == payload.new_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different")

        user.hashed_password = get_password_hash(payload.new_password)
        db.add(user)
        db.commit()

    def _issue_tokens(self, db: Session, user: User) -> TokenPair:
        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))

        token_record = RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(refresh_token),
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(token_record)

        stale_records = list(
            db.scalars(
                select(RefreshToken)
                .where(RefreshToken.user_id == user.id)
                .order_by(RefreshToken.created_at.desc())
                .offset(settings.max_active_sessions_per_user)
            ).all()
        )
        for record in stale_records:
            db.delete(record)

        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    def _find_refresh_token_record(self, db: Session, refresh_token: str) -> RefreshToken | None:
        token_hash = hash_refresh_token(refresh_token)
        # Legacy support: accept older plaintext tokens already stored in DB and rotate to hashed on next refresh.
        return db.scalar(
            select(RefreshToken).where(
                or_(
                    RefreshToken.token == token_hash,
                    RefreshToken.token == refresh_token,
                )
            )
        )


auth_service = AuthService()
