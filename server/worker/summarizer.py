"""
Document summarization module.

Generates a two-sentence description of an investment document using an LLM.
Falls back to extracting the first two sentences from the raw text when
the LLM is unavailable (no API key or network error).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a financial analyst assistant. Be concise and precise. "
    "Write in plain, professional English."
)
_USER_PROMPT = "Summarize this investment document in two sentences:\n\n{text}"


def generate_description(text: str) -> Optional[str]:
    """
    Generate a short two-sentence description of the document.

    Args:
        text: Full extracted document text (truncated internally to 3 000 chars).

    Returns:
        A two-sentence summary string, or a plain-text fallback, or None.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set – using fallback summarization")
        return _fallback_summary(text)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        truncated = text[:3000]
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT.format(text=truncated)},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
        logger.info("Document summary generated via LLM")
        return summary
    except Exception as exc:
        logger.error(f"LLM summarization failed: {exc}")
        return _fallback_summary(text)


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_summary(text: str) -> Optional[str]:
    """
    Return the first two meaningful sentences from the document.
    Used when the LLM is unavailable.
    """
    if not text:
        return None
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
    if sentences:
        return ". ".join(sentences[:2]) + "."
    return text[:200] if text else None
