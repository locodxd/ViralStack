"""
Gmail API client with per-account OAuth2 support.

Each registered account can have its own Gmail
OAuth token, allowing independent email management per account.
"""
import base64
import logging
from pathlib import Path
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config.settings import get_gmail_token_path_for, list_account_ids

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _get_credentials(account: str) -> Credentials:
    """Get or refresh Gmail OAuth credentials for a specific account."""
    token_path = Path(get_gmail_token_path_for(account))
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                f"Gmail not authenticated for account '{account}'. "
                f"Run: python scripts/setup_gmail.py {account}"
            )

        token_path.write_text(creds.to_json())

    return creds


def _get_service(account: str):
    """Build Gmail API service for a specific account."""
    creds = _get_credentials(account)
    return build("gmail", "v1", credentials=creds)


def fetch_unread_emails(account: str, max_results: int = 20) -> list:
    """Fetch unread emails from inbox for a specific account.

    Returns list of dicts with: id, thread_id, sender, subject, body, date.
    """
    service = _get_service(account)

    results = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return []

    emails = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_ref["id"],
            format="full",
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

        # Extract body
        body = ""
        payload = msg["payload"]
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
        elif "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        emails.append({
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "body": body[:5000],  # Truncate for API limits
            "date": headers.get("date", ""),
            "account": account,
        })

    return emails


def get_thread(account: str, thread_id: str) -> list:
    """Get all messages in a thread for context."""
    service = _get_service(account)
    thread = service.users().threads().get(userId="me", id=thread_id).execute()

    messages = []
    for msg in thread.get("messages", []):
        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

        body = ""
        payload = msg["payload"]
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
        elif "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        messages.append({
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "body": body[:3000],
            "date": headers.get("date", ""),
        })

    return messages


def send_reply(account: str, thread_id: str, message_id: str, to: str, subject: str, body: str):
    """Send a reply in a thread using a specific account."""
    service = _get_service(account)

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={
            "raw": raw,
            "threadId": thread_id,
        },
    ).execute()

    logger.info("[%s] Reply sent to %s in thread %s", account, to, thread_id)


def mark_as_read(account: str, message_id: str):
    """Mark a message as read."""
    service = _get_service(account)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def mark_as_important(account: str, message_id: str):
    """Mark a message as important."""
    service = _get_service(account)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": ["IMPORTANT"]},
    ).execute()


async def poll_and_process_account(account: str):
    """Poll for new emails and process them for a specific account."""
    from email_agent.classifier import classify_email
    from email_agent.responder import handle_email

    logger.info("[%s] Polling for new emails...", account)

    try:
        emails = fetch_unread_emails(account)
        logger.info("[%s] Found %d unread emails", account, len(emails))

        for email in emails:
            try:
                category = await classify_email(email)
                await handle_email(email, category, account)
                mark_as_read(account, email["id"])
            except Exception as e:
                logger.error("[%s] Error processing email '%s': %s",
                             account, email["subject"], e)

    except Exception as e:
        logger.error("[%s] Email polling failed: %s", account, e)
        from core import discord_alerts
        discord_alerts.send_error(
            f"Email polling fallo para {account}: {e}",
            exception=e,
            account=account,
        )


async def poll_and_process():
    """Poll all accounts for new emails. Called by scheduler."""
    for account in list_account_ids():
        try:
            await poll_and_process_account(account)
        except Exception as e:
            logger.error("[%s] Email polling skipped: %s", account, e)
