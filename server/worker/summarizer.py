"""
Document summarization module.

Generates a two-sentence description of an investment document using an LLM.
Falls back to extracting the first two sentences from the raw text when
the LLM is unavailable (no API key or network error).
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_LLM_RETRIES = 3
_LLM_RETRY_BACKOFF = (5.0, 15.0, 30.0)   # wait (seconds) before attempt n+1

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

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_LLM_RETRIES + 1):
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
            last_exc = exc
            if attempt < _MAX_LLM_RETRIES:
                wait = _LLM_RETRY_BACKOFF[min(attempt - 1, len(_LLM_RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"LLM summarization attempt {attempt}/{_MAX_LLM_RETRIES} failed: {exc} "
                    f"\u2014 retrying in {wait:.0f}s"
                )
                time.sleep(wait)
    logger.error(f"LLM summarization failed after {_MAX_LLM_RETRIES} attempts: {last_exc}")
    return _fallback_summary(text)


# ── Fallback ──────────────────────────────────────────────────────────────────

def text_summary(text: str) -> Optional[str]:
    """Extract a two-sentence summary from raw text without any LLM call."""
    return _fallback_summary(text)


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
