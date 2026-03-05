"""
Deal attribution and resolution module.

Responsible for:
  - Extracting a deal name candidate from a file's Drive folder path (Signal A)
  - Normalizing deal names for deduplication
  - Looking up or creating Deal records in the database

Signal priority (highest → lowest):
  1. Folder path signal — most reliable; directly reflects how the user organised their Drive
  2. LLM signal        — extracted from document content by batch_analyzer
  3. None              — document stored ungrouped ("Uncategorized" in UI)
"""

import re
import logging
import sys
import os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from rapidfuzz import fuzz as _fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RAPIDFUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

# Minimum fuzzy similarity (0–100) to consider two deal names the same deal.
# token_set_ratio handles word reordering and subset matches, e.g.:
#   "Acme" vs "Acme Robotics"  → ~89
#   "Beta Health" vs "Beta"    → ~86
#   "Acme" vs "Zeta Energy"   → ~22
FUZZY_THRESHOLD = 85

# ── Generic folder names to ignore ───────────────────────────────────────────

_GENERIC: set[str] = {
    "docs", "documents", "files", "file", "archive", "archives", "archived",
    "misc", "miscellaneous", "other", "others", "temp", "tmp", "new", "old",
    "uploads", "upload", "download", "downloads", "shared", "share",
    "q1", "q2", "q3", "q4", "h1", "h2",
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    # common VC-firm internal folder names
    "portfolio", "pipeline", "deals", "deal", "investments", "investment",
    "prospects", "prospect", "active", "closed", "leads",
    "inbox", "review", "reviewed", "pending",
    # version/date tokens
    "v1", "v2", "v3", "v4", "v5",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026",
}

# Company suffix patterns to strip before normalizing
_SUFFIX_RE = re.compile(
    r"\s*(,\s*)?(inc\.?|incorporated|ltd\.?|limited|llc\.?|llp\.?|corp\.?|"
    r"corporation|co\.?|group|holdings|ventures|capital|partners|fund)\s*$",
    re.IGNORECASE,
)

# Characters to strip when building the lookup key
_NON_ALNUM = re.compile(r"[^a-z0-9]")


# ── Public interface ──────────────────────────────────────────────────────────

def extract_deal_from_folder_path(folder_path: Optional[str]) -> Optional[str]:
    """
    Given a slash-separated folder path string (e.g. "Portfolio/Acme Corp/Q1 2025"),
    return the most likely deal name, or None if only generic segments are found.

    Strategy: walk segments from left to right; return the first non-generic one.
    This means "Portfolio/Acme Corp/Q1 2025" → "Acme Corp" (Portfolio is generic,
    Q1 2025 is generic, Acme Corp is the meaningful middle segment).
    """
    if not folder_path:
        return None

    segments = [s.strip() for s in folder_path.split("/") if s.strip()]
    for segment in segments:
        key = _normalize_key(segment)
        if key and key not in _GENERIC and not key.isdigit() and len(key) >= 2:
            return segment.title()
    return None


def normalize_deal_name(name: str) -> str:
    """Return the normalized display name: stripped of company suffixes, title-cased."""
    name = _SUFFIX_RE.sub("", name.strip())
    return name.strip().title()


def _normalize_key(name: str) -> str:
    """Return lowercase alphanumeric key for deduplication (also strips suffixes)."""
    name = _SUFFIX_RE.sub("", name.lower())
    return _NON_ALNUM.sub("", name)


def _fuzzy_find_deal(db: Session, user_id: int, key: str, raw_name: str):
    """
    Scan all existing deals for this user and return the best fuzzy match
    above FUZZY_THRESHOLD, or None if nothing is close enough.

    Uses token_set_ratio which handles word reordering and subset matches:
      "Acme"          vs "Acme Robotics"   → ~89  ✓ match
      "Beta Health"   vs "Beta"            → ~86  ✓ match
      "Acme Robotics" vs "Acme Inc"        → ~80  ✓ match (above threshold)
      "Acme"          vs "Zeta Energy"     → ~22  ✗ no match
    """
    if not _RAPIDFUZZ_AVAILABLE:
        return None

    from app.models.deal import Deal

    existing = db.query(Deal).filter(Deal.user_id == user_id).all()
    if not existing:
        return None

    best_deal = None
    best_score = 0

    for deal in existing:
        score = _fuzz.token_set_ratio(key, deal.name_key)
        if score > best_score:
            best_score = score
            best_deal = deal

    if best_score >= FUZZY_THRESHOLD:
        logger.info(
            f"Fuzzy match: '{raw_name}' → '{best_deal.name}' "
            f"(score={best_score}, threshold={FUZZY_THRESHOLD})"
        )
        return best_deal

    return None


def get_or_create_deal(db: Session, user_id: int, raw_name: str):
    """
    Look up a Deal by normalized key for this user; create it if not found.
    Returns the Deal ORM object.

    Deduplication: "Acme Corp", "ACME INC", and "acme" all produce key "acme"
    and resolve to the same Deal row.
    """
    from app.models.deal import Deal

    display_name = normalize_deal_name(raw_name)
    key = _normalize_key(raw_name)

    if not key or len(key) < 2:
        return None

    deal = (
        db.query(Deal)
        .filter(Deal.user_id == user_id, Deal.name_key == key)
        .first()
    )
    if deal:
        return deal

    # ── Fuzzy pass: catch near-duplicates before creating a new row ──────────
    fuzzy_match = _fuzzy_find_deal(db, user_id, key, raw_name)
    if fuzzy_match:
        return fuzzy_match

    try:
        deal = Deal(user_id=user_id, name=display_name, name_key=key)
        db.add(deal)
        db.commit()
        db.refresh(deal)
        logger.info(f"Created new deal: '{display_name}' (key='{key}') for user {user_id}")
        return deal
    except IntegrityError:
        # Another concurrent insert beat us — roll back and fetch the winner
        db.rollback()
        return (
            db.query(Deal)
            .filter(Deal.user_id == user_id, Deal.name_key == key)
            .first()
        )
