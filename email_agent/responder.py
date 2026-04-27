import logging
from google.genai import types
from core.key_rotation import gemini_rotator
from core.db import get_session
from core.models import EmailThread
from core import discord_alerts
from config.settings import PRICING, settings, ACCOUNTS
from email_agent import gmail_client, thread_tracker

logger = logging.getLogger(__name__)

# ---- English prompts ----
_SPONSOR_PROMPT_EN = """You are the manager of a short-form video content creator. Reply to this potential sponsor's email.

CONTEXT:
- We are a viral short-form content channel across the platforms we operate
- Our rates:
  * 15-second mention: ${mencion_15s} USD
  * Dedicated video: ${video_dedicado} USD
  * Link in bio for 1 month: ${link_bio_1mes} USD
- Tone: professional but friendly

PREVIOUS THREAD:
{thread_context}

CURRENT EMAIL:
From: {sender}
Subject: {subject}
{body}

Write a professional response that:
1. Thanks them for their interest
2. Presents the rates
3. Asks what type of collaboration they're interested in
4. Includes a CTA to schedule a call or confirm the deal

Only return the response text."""

_COLLAB_PROMPT_EN = """You are a short-form video content creator. Reply to this fellow creator who wants to collaborate.

PREVIOUS THREAD:
{thread_context}

CURRENT EMAIL:
From: {sender}
Subject: {subject}
{body}

Write a casual, enthusiastic response that:
1. Shows interest in the collaboration
2. Proposes a specific collab format (duet, joint video, content swap)
3. Briefly mentions channel stats
4. Suggests next steps

Tone: casual, friendly, between fellow creators. Only the response text."""

_FAN_RESPONSE_EN = """Thank you so much for your message!

I really appreciate that you enjoy the content. Comments like yours are what motivate me to keep creating.

See you in the next video! Don't forget to follow so you don't miss anything."""

# ---- Spanish prompts ----
_SPONSOR_PROMPT_ES = """Eres el manager de un creador de contenido short-form. Responde a este email de un sponsor potencial.

CONTEXTO:
- Somos un canal de contenido viral short-form en las plataformas donde operamos
- Nuestras tarifas son:
  * Mención de 15 segundos: ${mencion_15s} USD
  * Video dedicado: ${video_dedicado} USD
  * Link en bio por 1 mes: ${link_bio_1mes} USD
- Tono: profesional pero amigable

HILO DE CONVERSACIÓN PREVIO:
{thread_context}

EMAIL ACTUAL:
De: {sender}
Asunto: {subject}
{body}

Escribe una respuesta profesional en español que:
1. Agradezca el interés
2. Presente las tarifas
3. Pregunte qué tipo de colaboración les interesa
4. Incluya un CTA para agendar una llamada o confirmar el deal

Solo devuelve el texto de la respuesta."""

_COLLAB_PROMPT_ES = """Eres un creador de contenido short-form. Responde a este email de otro creador que quiere colaborar.

HILO PREVIO:
{thread_context}

EMAIL ACTUAL:
De: {sender}
Asunto: {subject}
{body}

Escribe una respuesta casual y entusiasta en español que:
1. Muestre interés en la colaboración
2. Proponga un formato específico (dueto, video juntos, intercambio de contenido)
3. Mencione brevemente las estadísticas del canal
4. Sugiera próximos pasos

Tono: casual, amigable, entre colegas creadores. Solo el texto de la respuesta."""

_FAN_RESPONSE_ES = """¡Muchas gracias por tu mensaje!

Me alegra mucho que disfrutes del contenido. Comentarios como el tuyo son los que me motivan a seguir creando.

¡Nos vemos en el próximo video! No olvides seguirme para no perderte nada."""


def _get_prompts():
    """Get the correct prompts based on language setting."""
    if settings.is_english:
        return _SPONSOR_PROMPT_EN, _COLLAB_PROMPT_EN, _FAN_RESPONSE_EN
    return _SPONSOR_PROMPT_ES, _COLLAB_PROMPT_ES, _FAN_RESPONSE_ES


async def _generate_response(prompt: str) -> str:
    """Generate a response using Gemini with key+model rotation."""

    def build_request(client, model_name):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=500,
            ),
        )

    # Use Flash for email responses (good quality, not expensive)
    response, _ = gemini_rotator.call(
        build_request,
        preferred_models=["gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-flash"],
    )
    return response.text.strip()


async def handle_email(email: dict, category: str, account: str):
    """Handle an email based on its classification."""
    sender = email.get("sender", "")
    subject = email.get("subject", "")
    thread_id = email.get("thread_id", "")
    message_id = email.get("id", "")
    body = email.get("body", "")

    sponsor_prompt, collab_prompt, fan_response = _get_prompts()

    # Save to database
    with get_session() as session:
        thread_record = session.query(EmailThread).filter_by(
            gmail_thread_id=thread_id
        ).first()

        if not thread_record:
            thread_record = EmailThread(
                gmail_thread_id=thread_id,
                gmail_message_id=message_id,
                account=account,
                sender=sender,
                subject=subject,
                body_preview=body[:500],
                category=category,
            )
            session.add(thread_record)
        else:
            thread_record.category = category
            thread_record.account = account

    # Get thread context for contextual replies
    context = thread_tracker.get_thread_context(account, thread_id)

    if category == "spam":
        logger.info("[%s] Ignoring spam from %s: %s", account, sender, subject)
        return

    elif category == "legal":
        logger.warning("[%s] LEGAL email detected from %s: %s", account, sender, subject)
        gmail_client.mark_as_important(account, message_id)

        acc_display = ACCOUNTS.get(account, {}).get("display_name", account)
        discord_alerts.send_urgent(
            f"**EMAIL LEGAL RECIBIDO — {acc_display}**\n\n"
            f"**De:** {sender}\n"
            f"**Asunto:** {subject}\n\n"
            f"**Contenido:**\n{body[:1500]}\n\n"
            f"NO se envió auto-respuesta. Revisar urgentemente.",
            account=account,
        )

        with get_session() as session:
            thread_record = session.query(EmailThread).filter_by(
                gmail_thread_id=thread_id
            ).first()
            if thread_record:
                thread_record.needs_attention = True

        return

    elif category == "sponsor":
        prompt = sponsor_prompt.format(
            mencion_15s=PRICING["mencion_15s"],
            video_dedicado=PRICING["video_dedicado"],
            link_bio_1mes=PRICING["link_bio_1mes"],
            thread_context=context,
            sender=sender,
            subject=subject,
            body=body[:2000],
        )
        response_text = await _generate_response(prompt)

    elif category == "collab":
        prompt = collab_prompt.format(
            thread_context=context,
            sender=sender,
            subject=subject,
            body=body[:2000],
        )
        response_text = await _generate_response(prompt)

    elif category == "fan":
        response_text = fan_response

    else:  # "otro"
        logger.info("[%s] Unclassified email from %s: %s (skipping)", account, sender, subject)
        return

    # Send reply
    try:
        gmail_client.send_reply(
            account=account,
            thread_id=thread_id,
            message_id=message_id,
            to=sender,
            subject=subject,
            body=response_text,
        )

        # Update database
        with get_session() as session:
            thread_record = session.query(EmailThread).filter_by(
                gmail_thread_id=thread_id
            ).first()
            if thread_record:
                thread_record.auto_responded = True
                thread_record.response_text = response_text

        # Save to thread tracker for future context
        thread_tracker.save_response(thread_id, response_text)

        acc_display = ACCOUNTS.get(account, {}).get("display_name", account)
        discord_alerts.send_info(
            f"Email [{category}] auto-respondido — {acc_display}\n"
            f"De: {sender}\nAsunto: {subject}",
            account=account,
        )

    except Exception as e:
        logger.error("[%s] Failed to send reply to %s: %s", account, sender, e)
        discord_alerts.send_error(
            f"Error enviando respuesta a {sender}: {e}",
            exception=e,
            account=account,
        )
