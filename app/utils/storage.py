from __future__ import annotations

from pathlib import Path
from uuid import uuid4


AVATAR_MAX_BYTES = 2 * 1024 * 1024
ALLOWED_AVATAR_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def avatars_directory() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    path = base_dir / "storage" / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_avatar_file_name(user_id: int, original_name: str | None) -> str:
    extension = ".jpg"
    if original_name:
        suffix = Path(original_name).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            extension = suffix if suffix != ".jpeg" else ".jpg"
    return f"user-{user_id}-{uuid4().hex}{extension}"


def save_avatar_bytes(user_id: int, data: bytes, original_name: str | None) -> str:
    directory = avatars_directory()
    file_name = build_avatar_file_name(user_id, original_name)
    target = directory / file_name
    target.write_bytes(data)
    return f"/storage/avatars/{file_name}"