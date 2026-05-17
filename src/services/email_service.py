"""
AWS SES email service for DramValue.

Handles all outbound email: verification, password reset,
price alerts, and admin notifications.
"""

import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def _ses_client():
    settings = get_settings()
    return boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _sender() -> str:
    settings = get_settings()
    return f"{settings.email_from_name} <{settings.email_from}>"


def _send(to: str, subject: str, html: str, text: str) -> bool:
    """Send a single email via SES. Returns True on success."""
    try:
        _ses_client().send_email(
            Source=_sender(),
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html, "Charset": "UTF-8"},
                    "Text": {"Data": text, "Charset": "UTF-8"},
                },
            },
        )
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except ClientError as e:
        logger.error(f"SES ClientError sending to {to}: {e.response['Error']['Message']}")
    except BotoCoreError as e:
        logger.error(f"SES BotoCoreError sending to {to}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending email to {to}: {e}")
    return False


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

_BASE_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: #f9f6f2; margin: 0; padding: 0; }}
  .wrap {{ max-width: 560px; margin: 32px auto; background: #fff; border: 1px solid #e0d8ce; border-radius: 8px; padding: 40px; }}
  .logo {{ font-family: Georgia, serif; font-size: 22px; color: #a0622a; font-weight: bold; margin-bottom: 28px; }}
  h1 {{ font-family: Georgia, serif; font-size: 22px; color: #1a1208; margin: 0 0 16px; }}
  p {{ color: #5a4a38; font-size: 15px; line-height: 1.6; margin: 0 0 14px; }}
  .btn {{ display: inline-block; padding: 12px 28px; background: #a0622a; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; margin: 8px 0 20px; }}
  .note {{ font-size: 12px; color: #8c7a68; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0d8ce; }}
  .price-row {{ background: #f9f6f2; border: 1px solid #e0d8ce; border-radius: 6px; padding: 16px; margin: 16px 0; }}
  .price-big {{ font-size: 28px; font-weight: bold; color: #2d6e2d; font-variant-numeric: tabular-nums; }}
  .price-label {{ font-size: 12px; color: #8c7a68; }}
</style></head>
<body><div class="wrap">
  <div class="logo">DramValue</div>
  {body}
  <p class="note">You received this email from DramValue. If you didn't expect it, you can safely ignore it.</p>
</div></body>
</html>
"""


def send_verification_email(to_email: str, token: str, display_name: str, base_url: str = "https://dramvalue.com") -> bool:
    """Send email verification link after registration."""
    verify_url = f"{base_url}/auth/verify-email?token={token}"
    subject = "Verify your DramValue email"
    body = f"""
      <h1>Welcome, {display_name}</h1>
      <p>Click below to verify your email address and activate your account.</p>
      <a href="{verify_url}" class="btn">Verify Email</a>
      <p>This link expires in 24 hours.</p>
    """
    text = (
        f"Welcome to DramValue, {display_name}!\n\n"
        f"Verify your email: {verify_url}\n\n"
        "This link expires in 24 hours."
    )
    return _send(to_email, subject, _BASE_HTML.format(body=body), text)


def send_password_reset_email(to_email: str, token: str, display_name: str, base_url: str = "https://dramvalue.com") -> bool:
    """Send password reset link."""
    reset_url = f"{base_url}/auth/reset-password?token={token}"
    subject = "Reset your DramValue password"
    body = f"""
      <h1>Password reset</h1>
      <p>Hi {display_name} &mdash; someone requested a password reset for your account.</p>
      <a href="{reset_url}" class="btn">Reset Password</a>
      <p>This link expires in 1 hour. If you didn&apos;t request this, ignore this email and your password stays the same.</p>
    """
    text = (
        f"Hi {display_name},\n\nReset your password: {reset_url}\n\n"
        "This link expires in 1 hour. Ignore this email if you didn't request it."
    )
    return _send(to_email, subject, _BASE_HTML.format(body=body), text)


def send_price_alert_email(
    to_email: str,
    display_name: str,
    bottle_name: str,
    alert_type: str,
    target_price: float | None,
    current_price: float,
    bottle_url: str,
) -> bool:
    """Notify a user that their price alert has triggered."""
    if alert_type == "any_sale":
        trigger_line = f"<strong>{bottle_name}</strong> has a new recorded sale."
        trigger_text = f"{bottle_name} has a new recorded sale."
    elif target_price is not None:
        direction = "dropped below" if "below" in alert_type else "reached"
        trigger_line = f"<strong>{bottle_name}</strong> has {direction} your target of <strong>${target_price:,.0f}</strong>."
        trigger_text = f"{bottle_name} has {direction} your target of ${target_price:,.0f}."
    else:
        trigger_line = f"<strong>{bottle_name}</strong> price alert triggered."
        trigger_text = f"{bottle_name} price alert triggered."

    subject = f"Price alert: {bottle_name[:60]}"
    body = f"""
      <h1>Your alert fired</h1>
      <p>Hi {display_name} &mdash; {trigger_line}</p>
      <div class="price-row">
        <div class="price-big">${current_price:,.0f}</div>
        <div class="price-label">Current recorded price</div>
      </div>
      <a href="{bottle_url}" class="btn">View Price History</a>
      <p>Prices are aggregated from auction records and may lag real-time auctions by a few hours.</p>
    """
    text = (
        f"Hi {display_name},\n\n"
        f"{trigger_text}\n"
        f"Current price: ${current_price:,.0f}\n\n"
        f"View details: {bottle_url}"
    )
    return _send(to_email, subject, _BASE_HTML.format(body=body), text)


def send_admin_notification(subject: str, body_text: str) -> bool:
    """Send a plain-text notification to the admin."""
    settings = get_settings()
    admin = settings.admin_email
    html_body = f"<h1>{subject}</h1><pre style='font-family:monospace;font-size:13px;color:#3a2a1a;white-space:pre-wrap;'>{body_text}</pre>"
    return _send(admin, f"[DramValue] {subject}", _BASE_HTML.format(body=html_body), body_text)
