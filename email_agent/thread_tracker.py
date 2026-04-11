import logging
from core.db import get_session
from core.models import EmailThread

logger = logging.getLogger(__name__)


def get_thread_context(account: str, thread_id: str) -> str:
    """Get the full conversation context for a thread.

    Combines Gmail API data with our stored responses from the database.
    Returns a formatted string of the conversation history.
    """
    from email_agent import gmail_client

    try:
        messages = gmail_client.get_thread(account, thread_id)
    except Exception as e:
        logger.warning("[%s] Could not fetch thread %s: %s", account, thread_id, e)
        return "No prior context available."

    if not messages or len(messages) <= 1:
        return "This is the first message in the thread."

    context_parts = []
    for msg in messages[:-1]:  # Exclude the current message
        sender = msg.get("sender", "Unknown")
        body = msg.get("body", "")[:500]
        date = msg.get("date", "")
        context_parts.append(f"[{date}] {sender}:\n{body}")

    # Load our previous responses from database (persistent across restarts)
    with get_session() as session:
        db_thread = session.query(EmailThread).filter_by(
            gmail_thread_id=thread_id
        ).first()
        if db_thread and db_thread.response_text:
            context_parts.append(f"[Our response]:\n{db_thread.response_text[:500]}")

    return "\n---\n".join(context_parts) if context_parts else "No prior context available."


def save_response(thread_id: str, response_text: str):
    """Save our response to the database for persistent context across restarts."""
    with get_session() as session:
        db_thread = session.query(EmailThread).filter_by(
            gmail_thread_id=thread_id
        ).first()
        if db_thread:
            db_thread.response_text = response_text
            db_thread.auto_responded = True
            session.commit()
            logger.info("Saved response to DB for thread %s", thread_id)
        else:
            logger.warning(
                "Thread %s not found in DB — response saved only in Gmail",
                thread_id,
            )
