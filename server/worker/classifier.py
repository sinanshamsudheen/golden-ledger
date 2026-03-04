"""
Document classification module.

Classification strategy:
  1. Count keyword matches per document type (heuristic).
  2. If a type scores >= CONFIDENCE_THRESHOLD, return it.
  3. Otherwise fall back to an LLM call (GPT-4o-mini) for disambiguation.
  4. Default to "other" if LLM is unavailable or returns an unknown label.

Document types:
  pitch_deck | investment_report | deal_memo | financial_report | other
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Keyword dictionary ────────────────────────────────────────────────────────

_KEYWORDS: dict[str, list[str]] = {
    "pitch_deck": [
        "pitch deck",
        "investor presentation",
        "startup overview",
        "series a",
        "series b",
        "seed round",
        "company overview",
        "investment opportunity",
        "funding round",
        "venture capital",
        "go to market",
    ],
    "investment_report": [
        "investment report",
        "fund performance",
        "portfolio review",
        "returns analysis",
        "investment update",
        "portfolio update",
        "fund update",
        "lp update",
        "performance report",
        "quarterly performance",
    ],
    "deal_memo": [
        "deal memo",
        "investment memo",
        "deal analysis",
        "term sheet",
        "deal summary",
        "transaction memo",
        "investment thesis",
        "due diligence memo",
        "diligence summary",
        "deal overview",
    ],
    "financial_report": [
        "financial report",
        "income statement",
        "balance sheet",
        "cash flow",
        "annual report",
        "quarterly report",
        "p&l",
        "profit and loss",
        "financial statements",
        "revenue report",
        "ebitda",
        "financial summary",
    ],
}

_VALID_TYPES = set(_KEYWORDS.keys()) | {"other"}
_CONFIDENCE_THRESHOLD = 2  # minimum keyword hits to trust the heuristic


# ── Public interface ──────────────────────────────────────────────────────────

def classify_document(text: str, file_name: str = "") -> str:
    """
    Classify a document into one of the known investment document types.

    Args:
        text:      Extracted document text (full or truncated).
        file_name: Original file name for additional signal.

    Returns:
        One of: pitch_deck, investment_report, deal_memo, financial_report, other
    """
    haystack = (text[:3000] + " " + file_name).lower()
    scores = {doc_type: _count_hits(haystack, kws) for doc_type, kws in _KEYWORDS.items()}

    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]

    logger.debug(f"Heuristic scores: {scores}")

    if best_score >= _CONFIDENCE_THRESHOLD:
        logger.info(f"Classified as '{best_type}' (heuristic score={best_score})")
        return best_type

    logger.info(f"Low heuristic confidence ({best_score}), delegating to LLM")
    return _classify_with_llm(text[:2000], file_name) or "other"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_hits(haystack: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in haystack)


def _classify_with_llm(text: str, file_name: str) -> Optional[str]:
    """Delegate classification to OpenAI when the heuristic is uncertain."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set – skipping LLM classification")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "Classify this investment document into exactly one of these categories:\n"
            "pitch_deck, investment_report, deal_memo, financial_report, other\n\n"
            f"File name: {file_name}\n\n"
            f"Document excerpt:\n{text}\n\n"
            "Reply with only the category name, nothing else."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0,
        )
        label = response.choices[0].message.content.strip().lower()
        if label in _VALID_TYPES:
            logger.info(f"LLM classified document as '{label}'")
            return label
        logger.warning(f"LLM returned unexpected label '{label}', defaulting to 'other'")
        return "other"
    except Exception as exc:
        logger.error(f"LLM classification failed: {exc}")
        return None
