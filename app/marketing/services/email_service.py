"""
Email Service — campaign-routed email sending and AI follow-up generation.

Each campaign gets a unique inbound email: {campaign-slug}@mail.yourdomain.com
Outbound emails use the campaign address as From/Reply-To so replies route back.

Providers:
  - "sendgrid" — SendGrid Web API v3
  - "smtp" — Direct SMTP (Gmail, Outlook, etc.)
  - "log"  — Dev mode, prints to console (no emails sent)

AI features:
  - summarize_thread()   — Summarize an email+call thread using Claude
  - generate_followup()  — Draft AI follow-up based on conversation history
"""

import json
import logging
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Send and manage campaign-routed emails."""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        from_address: str | None = None,
        reply_to: str | None = None,
        html: str | None = None,
    ) -> dict:
        """
        Send an email via the configured provider.
        Returns {"sent": True, "message_id": "..."} on success.
        """
        sender = from_address or settings.email_from_address
        reply = reply_to or settings.email_reply_to or sender

        provider = settings.email_provider.lower()

        if provider == "sendgrid":
            return await self._send_sendgrid(to, subject, body, sender, reply, html)
        elif provider == "smtp":
            return await self._send_smtp(to, subject, body, sender, reply, html)
        else:
            # "log" mode — dev/testing
            logger.info(
                f"[EMAIL-LOG] To: {to} | From: {sender} | Reply-To: {reply}\n"
                f"  Subject: {subject}\n"
                f"  Body: {body[:200]}..."
            )
            return {"sent": True, "message_id": f"log-{id(body)}", "provider": "log"}

    async def _send_sendgrid(
        self, to: str, subject: str, body: str, sender: str, reply_to: str, html: str | None,
    ) -> dict:
        """Send via SendGrid Web API v3."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, ReplyTo

            message = Mail(
                from_email=sender,
                to_emails=to,
                subject=subject,
                plain_text_content=body,
                html_content=html,
            )
            message.reply_to = ReplyTo(reply_to)

            sg = SendGridAPIClient(settings.sendgrid_api_key)
            response = sg.send(message)

            message_id = response.headers.get("X-Message-Id", "")
            return {
                "sent": True,
                "message_id": message_id,
                "status_code": response.status_code,
                "provider": "sendgrid",
            }
        except Exception as e:
            logger.error(f"SendGrid send error: {e}")
            return {"sent": False, "error": str(e), "provider": "sendgrid"}

    async def _send_smtp(
        self, to: str, subject: str, body: str, sender: str, reply_to: str, html: str | None,
    ) -> dict:
        """Send via direct SMTP."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = to
            msg["Reply-To"] = reply_to

            msg.attach(MIMEText(body, "plain"))
            if html:
                msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)

            return {"sent": True, "message_id": msg["Message-ID"] or "", "provider": "smtp"}
        except Exception as e:
            logger.error(f"SMTP send error: {e}")
            return {"sent": False, "error": str(e), "provider": "smtp"}

    def build_campaign_email(self, campaign_slug: str, domain: str = "mail.seojames.io") -> str:
        """Build campaign-specific email address: {slug}@{domain}."""
        safe_slug = campaign_slug.lower().replace(" ", "-")
        return f"{safe_slug}@{domain}"

    async def generate_followup(
        self,
        thread_summary: str,
        business_name: str,
        lead_name: str,
        tone: str = "professional",
    ) -> str:
        """
        Generate an AI follow-up email draft based on conversation history.
        Uses Claude CLI for generation.
        """
        from app.core.services.anthropic_service import anthropic_service

        system = "You write concise, natural follow-up emails for small businesses. Return only the email body — no subject line."
        prompt = (
            f"You are writing a follow-up email on behalf of {business_name}.\n"
            f"The recipient is {lead_name}.\n"
            f"Tone: {tone}.\n\n"
            f"Here is a summary of the conversation so far:\n{thread_summary}\n\n"
            f"Write a brief, natural follow-up email (2-3 paragraphs max). "
            f"Reference specific details from the conversation. "
            f"End with a clear call to action. "
            f"Return ONLY the email body text, no subject line."
        )

        try:
            return await anthropic_service.chat(system_prompt=system, message=prompt)
        except Exception as e:
            logger.error(f"AI follow-up generation failed: {e}")
            return ""

    async def summarize_thread(
        self,
        interactions_text: str,
        business_name: str,
    ) -> str:
        """
        Summarize an email/call thread using Claude.
        Returns a concise summary of the conversation.
        """
        from app.core.services.anthropic_service import anthropic_service

        system = "You summarize conversation threads for small business CRM. Be concise and factual."
        prompt = (
            f"Summarize this conversation thread for {business_name}.\n"
            f"Include: key topics discussed, any quotes given, action items, "
            f"and current status of the relationship.\n\n"
            f"Thread:\n{interactions_text}\n\n"
            f"Write a concise 2-3 sentence summary."
        )

        try:
            return await anthropic_service.chat(system_prompt=system, message=prompt)
        except Exception as e:
            logger.error(f"Thread summarization failed: {e}")
            return ""


email_service = EmailService()
