from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kyc_record import KYCRecord
from app.models.user import User
from app.schemas.kyc import KYCResponse, KYCSubmitRequest


class KYCService:
    def submit(self, db: Session, user: User, payload: KYCSubmitRequest) -> KYCResponse:
        record = db.scalar(select(KYCRecord).where(KYCRecord.user_id == user.id))
        if record is None:
            record = KYCRecord(
                user_id=user.id,
                status="pending",
                document_type=payload.document_type,
                document_id=payload.document_id,
                notes=payload.notes,
            )
            db.add(record)
        else:
            record.status = "pending"
            record.document_type = payload.document_type
            record.document_id = payload.document_id
            record.notes = payload.notes
            record.verified_at = None

        db.commit()
        db.refresh(record)
        return KYCResponse.model_validate(record)

    def get_status(self, db: Session, user: User) -> KYCResponse | None:
        record = db.scalar(select(KYCRecord).where(KYCRecord.user_id == user.id))
        if record is None:
            return None
        return KYCResponse.model_validate(record)


kyc_service = KYCService()
