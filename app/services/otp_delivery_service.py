from __future__ import annotations

import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.core.config import settings

try:
    from twilio.rest import Client
except Exception:  # pragma: no cover
    Client = None


class OTPDeliveryService:
    def send_email_otp(self, email: str, otp_code: str, expires_in_minutes: int) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SMTP settings are not configured")

        message = EmailMessage()
        message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        message["To"] = email
        message["Subject"] = "Your Algo Trading verification code"
        message.set_content(
            "\n".join(
                [
                    "Hi,",
                    "",
                    f"Your one-time verification code is: {otp_code}",
                    f"This code expires in {expires_in_minutes} minutes.",
                    "",
                    "If you did not request this code, please ignore this email.",
                    "",
                    "Regards,",
                    settings.project_name,
                ]
            )
        )

        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
                self._smtp_auth(server)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            self._smtp_auth(server)
            server.send_message(message)

    def send_phone_otp(self, phone_number: str, otp_code: str, expires_in_minutes: int) -> None:
        if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_phone_number:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Twilio settings are not configured")
        if Client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Twilio SDK is not installed")

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        body = (
            f"{settings.project_name}: Your verification code is {otp_code}. "
            f"It expires in {expires_in_minutes} minutes."
        )
        client.messages.create(body=body, from_=settings.twilio_phone_number, to=phone_number)

    def _smtp_auth(self, server: smtplib.SMTP) -> None:
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)


otp_delivery_service = OTPDeliveryService()
