import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"


def send_verification_email(email: str, verification_link: str) -> None:
    """Send the email-verification link.

    In dev (no RESEND_API_KEY) the link is logged so the flow is testable.
    In production the email goes through Resend's free tier.
    """
    if settings.resend_api_key:
        try:
            httpx.post(
                RESEND_API,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.resend_from,
                    "to": [email],
                    "subject": "Verify your CreatorOS account",
                    "text": f"Verify your email: {verification_link}",
                },
            ).raise_for_status()
        except httpx.HTTPError:
            logger.exception("failed to send verification email to %s", email)
        return
    logger.info("DEV verification link for %s: %s", email, verification_link)
