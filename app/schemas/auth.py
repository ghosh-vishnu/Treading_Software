from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


PASSWORD_COMPLEXITY_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$")


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


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


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    username: str | None = None
    phone: str | None = None
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
    gender: str | None = None
    age: int | None = None
    experience_level: str | None = None
    bio: str | None = None
    public_profile: bool = True
    role: str
    is_active: bool
    created_at: datetime


class UserProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    gender: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=13, le=120)
    experience_level: str | None = Field(default=None, max_length=30)
    bio: str | None = Field(default=None, max_length=500)
    public_profile: bool = True

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
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
