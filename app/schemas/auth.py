from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


PASSWORD_COMPLEXITY_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$")


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        if not PASSWORD_COMPLEXITY_PATTERN.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one special character"
            )
        return value

    @field_validator("username")
    @classmethod
    def normalize_required_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,100}", normalized):
            raise ValueError("Username can only include lowercase letters, numbers, dot, underscore and hyphen")
        return normalized


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class SendSignupOTPRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", normalized):
            raise ValueError("Phone number must be in valid international format")
        return normalized


class VerifySignupOTPRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    email_challenge_id: str = Field(min_length=16, max_length=120)
    email_otp: str = Field(min_length=4, max_length=8)
    phone_challenge_id: str = Field(min_length=16, max_length=120)
    phone_otp: str = Field(min_length=4, max_length=8)

    @field_validator("phone")
    @classmethod
    def normalize_verify_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", normalized):
            raise ValueError("Phone number must be in valid international format")
        return normalized


class SignupOTPChallengeResponse(BaseModel):
    email_challenge_id: str
    phone_challenge_id: str
    expires_in_seconds: int
    debug_email_otp: str | None = None
    debug_phone_otp: str | None = None


class SignupCompleteRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    phone: str = Field(min_length=8, max_length=20)
    terms_accepted: bool
    email_challenge_id: str = Field(min_length=16, max_length=120)
    email_otp: str = Field(min_length=4, max_length=8)
    phone_challenge_id: str = Field(min_length=16, max_length=120)
    phone_otp: str = Field(min_length=4, max_length=8)

    @field_validator("full_name")
    @classmethod
    def normalize_signup_complete_full_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_signup_complete_password(cls, value: str) -> str:
        if not PASSWORD_COMPLEXITY_PATTERN.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one special character"
            )
        return value

    @field_validator("username")
    @classmethod
    def normalize_signup_complete_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,100}", normalized):
            raise ValueError("Username can only include lowercase letters, numbers, dot, underscore and hyphen")
        return normalized

    @field_validator("confirm_password")
    @classmethod
    def validate_signup_complete_confirm_password_complexity(cls, value: str) -> str:
        if not PASSWORD_COMPLEXITY_PATTERN.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one special character"
            )
        return value

    @field_validator("phone")
    @classmethod
    def normalize_signup_complete_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", normalized):
            raise ValueError("Phone number must be in valid international format")
        return normalized

    @field_validator("terms_accepted")
    @classmethod
    def validate_terms_accepted(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("You must accept terms and conditions")
        return value

    @field_validator("confirm_password")
    @classmethod
    def validate_password_match(cls, value: str, info):
        password = info.data.get("password")
        if password and value != password:
            raise ValueError("Password and confirm password must match")
        return value


class LoginOTPRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class VerifyLoginOTPRequest(BaseModel):
    challenge_id: str = Field(min_length=16, max_length=120)
    otp: str = Field(min_length=4, max_length=8)


class LoginOTPChallengeResponse(BaseModel):
    challenge_id: str
    channel: Literal["email", "phone"]
    expires_in_seconds: int
    debug_otp: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordOTPRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_forgot_password_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", normalized):
            raise ValueError("Phone number must be in valid international format")
        return normalized


class ForgotPasswordOTPChallengeResponse(BaseModel):
    email_challenge_id: str
    phone_challenge_id: str
    expires_in_seconds: int
    debug_email_otp: str | None = None
    debug_phone_otp: str | None = None


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    email_challenge_id: str = Field(min_length=16, max_length=120)
    email_otp: str = Field(min_length=4, max_length=8)
    phone_challenge_id: str = Field(min_length=16, max_length=120)
    phone_otp: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_reset_password_complexity(cls, value: str) -> str:
        if not PASSWORD_COMPLEXITY_PATTERN.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one special character"
            )
        return value

    @field_validator("phone")
    @classmethod
    def normalize_reset_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", normalized):
            raise ValueError("Phone number must be in valid international format")
        return normalized


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_complexity(cls, value: str) -> str:
        if not PASSWORD_COMPLEXITY_PATTERN.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one special character"
            )
        return value


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)


class TrustDeviceRequest(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SessionInfoResponse(BaseModel):
    id: int
    created_at: datetime
    expires_at: datetime
    is_current: bool
    is_trusted: bool = False
    device_name: str | None = None
    browser: str | None = None
    os: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class TrustedDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    device_fingerprint: str
    device_name: str | None = None
    browser: str | None = None
    os: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    trusted_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    username: str | None = None
    phone: str | None = None
    mobile: str | None = None
    country: str | None = None
    timezone: str | None = None
    avatar_url: str | None = None
    gender: str | None = None
    age: int | None = None
    experience_level: str | None = None
    bio: str | None = None
    public_profile: bool = True
    role: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenPair


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    username: str | None = None
    phone: str | None = None
    mobile: str | None = None
    country: str | None = None
    timezone: str | None = None
    avatar_url: str | None = None
    gender: str | None = None
    age: int | None = None
    experience_level: str | None = None
    bio: str | None = None
    public_profile: bool = True
    role: str
    is_active: bool
    created_at: datetime


class UserProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    mobile: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)
    gender: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=13, le=120)
    experience_level: str | None = Field(default=None, max_length=30)
    bio: str | None = Field(default=None, max_length=500)
    public_profile: bool | None = None

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.strip().split())

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if not re.fullmatch(r"[a-z0-9._-]{3,100}", normalized):
            raise ValueError("Username can only include lowercase letters, numbers, dot, underscore and hyphen")
        return normalized
