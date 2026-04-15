from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPair,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import auth_service


router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
@limiter.limit("10/minute")
def signup(request: Request, response: Response, payload: RegisterRequest, db: Session = Depends(get_db)):
    return auth_service.register(db, payload)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    return auth_service.login(db, payload)


@router.post("/refresh", response_model=TokenPair)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    auth_service.revoke_refresh_token(db, payload.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserProfileResponse)
@limiter.limit("60/minute")
def get_profile(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    return auth_service.get_profile(current_user)


@router.patch("/me", response_model=UserProfileResponse)
@limiter.limit("20/minute")
def update_profile(
    request: Request,
    response: Response,
    payload: UserProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return auth_service.update_profile(db, current_user, payload)


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit("10/minute")
def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    auth_service.change_password(db, current_user, payload)
    return MessageResponse(message="Password updated successfully")
