import logging
from google.genai import types
from core.key_rotation import gemini_rotator

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify the following email into exactly ONE of these categories:

- "spam" → ads, unwanted newsletters, junk mail
- "sponsor" → a brand or company wants to pay for a mention or commercial collaboration
- "collab" → another content creator wants to collaborate (not necessarily paid)
- "legal" → copyright, lawsuits, TikTok warnings, DMCA, legal claims
- "fan" → message from a follower, positive comment, fan question
- "otro" → anything that doesn't fit the categories above

EMAIL:
From: {sender}
Subject: {subject}
Body:
{body}

Reply with ONLY the category (a single lowercase word): spam, sponsor, collab, legal, fan, or otro.
"""


async def classify_email(email: dict) -> str:
    """Classify an email using Gemini with key+model rotation."""
    prompt = CLASSIFY_PROMPT.format(
        sender=email.get("sender", ""),
        subject=email.get("subject", ""),
        body=email.get("body", "")[:2000],
    )

    def build_request(client, model_name):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=10,
            ),
        )

    # Use Flash Lite for classification (cheapest, simple task) → Flash as fallback
    response, model_used = gemini_rotator.call(
        build_request,
        preferred_models=["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview", "gemini-2.5-flash"],
    )
    category = response.text.strip().lower().replace('"', '').replace("'", "")

    valid_categories = {"spam", "sponsor", "collab", "legal", "fan", "otro"}
    if category not in valid_categories:
        logger.warning("Unknown category '%s', defaulting to 'otro'", category)
        category = "otro"

    logger.info("Email '%s' from %s → %s (model=%s)",
                email.get("subject", ""), email.get("sender", ""), category, model_used)

    return category
