"""
Document classification module.

Classification strategy:
  1. Count keyword matches per document type (heuristic).
  2. If a type scores >= CONFIDENCE_THRESHOLD, return it.
  3. Otherwise signal low confidence so the caller can delegate to the batch LLM analyzer.

Document types:
  pitch_deck | investment_memo | prescreening_report | meeting_minutes
"""

import logging

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
        "go to market",
        "funding round",
        "venture capital",
    ],
    "investment_memo": [
        "investment memo",
        "ic memo",
        "investment committee",
        "deal memo",
        "deal analysis",
        "investment thesis",
        "due diligence memo",
        "diligence summary",
        "term sheet",
        "deal overview",
        "deal summary",
    ],
    "prescreening_report": [
        "pre-screening",
        "prescreening",
        "pre screening",
        "initial review",
        "deal screening",
        "opportunity assessment",
        "pipeline review",
        "first look",
        "screening report",
        "initial assessment",
    ],
    "meeting_minutes": [
        "meeting minutes",
        "board minutes",
        "minutes of meeting",
        "action items",
        "attendees",
        "meeting notes",
        "discussed",
        "resolved",
        "agenda",
        "follow-up items",
    ],
}

VALID_TYPES = set(_KEYWORDS.keys())
_CONFIDENCE_THRESHOLD = 2  # minimum keyword hits to trust the heuristic


# ── Public interface ──────────────────────────────────────────────────────────

def classify_document(text: str, file_name: str = "") -> tuple[str, bool]:
    """
    Classify a document into one of the known investment document types.

    Returns:
        (doc_type, confident) — if confident is False the caller should
        include this document in the batch LLM analysis.
    """
    haystack = (text[:3000] + " " + file_name).lower()
    scores = {doc_type: _count_hits(haystack, kws) for doc_type, kws in _KEYWORDS.items()}

    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]

    logger.debug(f"Heuristic scores for '{file_name}': {scores}")

    if best_score >= _CONFIDENCE_THRESHOLD:
        logger.info(f"'{file_name}' classified as '{best_type}' (heuristic score={best_score})")
        return best_type, True

    logger.info(f"'{file_name}' low heuristic confidence ({best_score}), needs LLM")
    return best_type, False  # best guess but not confident


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_hits(haystack: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in haystack)
