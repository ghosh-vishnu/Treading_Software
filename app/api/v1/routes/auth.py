from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginOTPChallengeResponse,
    LoginOTPRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SessionInfoResponse,
    RegisterRequest,
    SendSignupOTPRequest,
    SignupCompleteRequest,
    SignupOTPChallengeResponse,
    TokenPair,
    TrustedDeviceResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    VerifyLoginOTPRequest,
    VerifySignupOTPRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import auth_service


router = APIRouter()


def _request_metadata(request: Request) -> tuple[str | None, str | None, str | None]:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    request_id = request.headers.get("x-request-id")
    return client_ip, user_agent, request_id


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


@router.post("/signup", response_model=AuthResponse)
@limiter.limit("10/minute")
def signup(
    request: Request,
    response: Response,
    payload: SignupCompleteRequest,
    db: Session = Depends(get_db),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    return auth_service.register(
        db,
        RegisterRequest(email=payload.email, full_name=payload.full_name, password=payload.password),
        otp_payload=VerifySignupOTPRequest(
            email=payload.email,
            phone=payload.phone,
            email_challenge_id=payload.email_challenge_id,
            email_otp=payload.email_otp,
            phone_challenge_id=payload.phone_challenge_id,
            phone_otp=payload.phone_otp,
        ),
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


@router.post("/signup/send-otp", response_model=SignupOTPChallengeResponse)
@limiter.limit("5/minute")
def send_signup_otp(request: Request, response: Response, payload: SendSignupOTPRequest, db: Session = Depends(get_db)):
    return auth_service.send_signup_otp(db, payload)


@router.post("/signup/verify-otp", response_model=MessageResponse)
@limiter.limit("10/minute")
def verify_signup_otp(request: Request, response: Response, payload: VerifySignupOTPRequest, db: Session = Depends(get_db)):
    auth_service.verify_signup_otp(db, payload)
    return MessageResponse(message="Signup OTP verified")


@router.post("/login", response_model=LoginOTPChallengeResponse)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    ip_address, user_agent, request_id = _request_metadata(request)
    return auth_service.login(db, payload, ip_address=ip_address, user_agent=user_agent, request_id=request_id)


@router.post("/login/send-otp", response_model=LoginOTPChallengeResponse)
@limiter.limit("10/minute")
def login_send_otp(request: Request, response: Response, payload: LoginOTPRequest, db: Session = Depends(get_db)):
    return auth_service.login_with_otp(db, payload)


@router.post("/login/verify-otp", response_model=AuthResponse)
@limiter.limit("10/minute")
def login_verify_otp(request: Request, response: Response, payload: VerifyLoginOTPRequest, db: Session = Depends(get_db)):
    ip_address, user_agent, request_id = _request_metadata(request)
    return auth_service.verify_login_otp(
        db,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


@router.post("/refresh", response_model=TokenPair)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    auth_service.revoke_refresh_token(db, payload.refresh_token, access_token=_bearer_token(request))
    return MessageResponse(message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    auth_service.logout_all_devices(db, current_user, access_token=_bearer_token(request))
    return MessageResponse(message="Logged out from all devices")


@router.delete("/me", response_model=MessageResponse)
def delete_account(
    request: Request,
    payload: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    auth_service.delete_account(
        db,
        current_user,
        payload,
        access_token=_bearer_token(request),
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    return MessageResponse(message="Account deleted successfully")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password(request: Request, response: Response, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    ip_address, user_agent, request_id = _request_metadata(request)
    debug_token = auth_service.forgot_password(db, payload, ip_address=ip_address, user_agent=user_agent, request_id=request_id)
    if settings.environment != "production" and debug_token:
        response.headers["X-Debug-Reset-Token"] = debug_token
    return MessageResponse(message="If the account exists, reset instructions have been generated")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("10/minute")
def reset_password(request: Request, response: Response, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    ip_address, user_agent, request_id = _request_metadata(request)
    auth_service.reset_password(db, payload, ip_address=ip_address, user_agent=user_agent, request_id=request_id)
    return MessageResponse(message="Password reset successful")


@router.get("/me", response_model=UserProfileResponse)
@limiter.limit("60/minute")
def get_profile(request: Request, response: Response, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return auth_service.get_profile(db, current_user)


@router.patch("/me", response_model=UserProfileResponse)
@limiter.limit("20/minute")
def update_profile(
    request: Request,
    response: Response,
    payload: UserProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    return auth_service.update_profile(
        db,
        current_user,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


@router.post("/me/avatar", response_model=UserProfileResponse)
@limiter.limit("20/minute")
def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    file_bytes = avatar.file.read()
    return auth_service.upload_avatar(
        db,
        current_user,
        file_bytes=file_bytes,
        file_name=avatar.filename,
        content_type=avatar.content_type,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit("10/minute")
def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    auth_service.change_password(
        db,
        current_user,
        payload,
        access_token=_bearer_token(request),
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    return MessageResponse(message="Password updated successfully")


@router.get("/sessions", response_model=list[SessionInfoResponse])
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return auth_service.list_sessions(db, current_user)


@router.post("/sessions/{session_id}/trust", response_model=TrustedDeviceResponse)
def trust_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    return auth_service.trust_session(
        db,
        current_user,
        session_id,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get("/trusted-devices", response_model=list[TrustedDeviceResponse])
def list_trusted_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return auth_service.list_trusted_devices(db, current_user)


@router.delete("/trusted-devices/{device_id}", response_model=MessageResponse)
def revoke_trusted_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent, request_id = _request_metadata(request)
    auth_service.revoke_trusted_device(
        db,
        current_user,
        device_id,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return MessageResponse(message="Trusted device revoked")


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_session(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    auth_service.revoke_session(db, current_user, session_id)
    return MessageResponse(message="Session revoked")
