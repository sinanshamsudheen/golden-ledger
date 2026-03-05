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
    # ── Pitch Deck ────────────────────────────────────────────────────────────
    # Covers investor decks, company presentations, fundraising narratives
    "pitch_deck": [
        # explicit deck language
        "pitch deck",
        "investor deck",
        "investor presentation",
        "investment presentation",
        "fundraising deck",
        "company deck",
        "overview deck",
        "series deck",
        # company intro
        "startup overview",
        "company overview",
        "executive summary",
        "about us",
        "our mission",
        "our vision",
        "problem statement",
        "solution overview",
        "value proposition",
        "product overview",
        "product demo",
        # market / traction
        "total addressable market",
        "tam",
        "serviceable addressable market",
        "sam",
        "market opportunity",
        "market size",
        "competitive landscape",
        "competitive advantage",
        "moat",
        "traction",
        "key metrics",
        "revenue growth",
        "monthly active users",
        "mau",
        "dau",
        "churn rate",
        "customer acquisition",
        # team
        "founding team",
        "management team",
        "advisory board",
        "key hires",
        # go-to-market
        "go to market",
        "go-to-market",
        "gtm strategy",
        "distribution channel",
        "sales motion",
        "channel partners",
        # funding
        "funding round",
        "fundraising",
        "seeking investment",
        "use of funds",
        "use of proceeds",
        "pre-seed",
        "seed round",
        "series a",
        "series b",
        "series c",
        "growth round",
        "bridge round",
        "venture capital",
        "vc backed",
        "lead investor",
        "co-investor",
        "cap table overview",
        # financial projections in deck context
        "financial projections",
        "revenue forecast",
        "path to profitability",
        "unit economics overview",
        # exit
        "exit strategy",
        "strategic acquirer",
        "ipo roadmap",
    ],

    # ── Investment Memo ───────────────────────────────────────────────────────
    # Covers IC memos, deal memos, due diligence reports, financial analyses
    "investment_memo": [
        # explicit memo language
        "investment memo",
        "investment memorandum",
        "ic memo",
        "investment committee",
        "deal memo",
        "deal analysis",
        "deal note",
        "deal recommendation",
        "investment thesis",
        "investment rationale",
        "investment summary",
        "investment overview",
        "investment recommendation",
        "investment decision",
        "deal overview",
        "deal summary",
        "deal review",
        # due diligence
        "due diligence",
        "due diligence memo",
        "due diligence report",
        "due diligence checklist",
        "diligence summary",
        "diligence findings",
        "diligence process",
        "diligence checklist",
        "dd report",
        "dd findings",
        "dd summary",
        "data room",
        "data room access",
        "legal due diligence",
        "financial due diligence",
        "commercial due diligence",
        "technical due diligence",
        # term sheet / legal
        "term sheet",
        "term sheet summary",
        "proposed terms",
        "valuation",
        "pre-money valuation",
        "post-money valuation",
        "liquidation preference",
        "anti-dilution",
        "pro-rata rights",
        "board seat",
        "protective provisions",
        "closing conditions",
        "representations and warranties",
        # financial analysis
        "financial summary",
        "financial analysis",
        "revenue analysis",
        "arr",
        "mrr",
        "annual recurring revenue",
        "monthly recurring revenue",
        "revenue breakdown",
        "revenue composition",
        "gross margin",
        "ebitda",
        "burn rate",
        "monthly burn",
        "cash runway",
        "runway",
        "cash on hand",
        "unit economics",
        "ltv",
        "cac",
        "ltv/cac",
        "ltv:cac",
        "cac payback",
        "payback period",
        "net revenue retention",
        "nrr",
        "gross revenue retention",
        "net dollar retention",
        "customer lifetime value",
        "average contract value",
        "acv",
        "annual contract value",
        "average revenue per user",
        "arpu",
        "gross profit",
        "operating leverage",
        "rule of 40",
        "magic number",
        # corporate / legal docs
        "cap table",
        "capitalization table",
        "stock ledger",
        "certificate of incorporation",
        "bylaws",
        "board consents",
        "material contracts",
        "employment agreements",
        "ip portfolio",
        "intellectual property",
        "litigation history",
        "regulatory compliance",
        "tax returns",
        "debt schedule",
        # risk / recommendation
        "key risks",
        "risk factors",
        "mitigants",
        "bear case",
        "bull case",
        "base case",
        "key assumptions",
        "sensitivity analysis",
        "financing recommended",
        "recommend proceeding",
        "recommend approval",
        "not recommended",
        "pass",
    ],

    # ── Prescreening Report ───────────────────────────────────────────────────
    # Covers initial opportunity assessments, pipeline reviews, first looks
    "prescreening_report": [
        # explicit prescreening language
        "pre-screening",
        "prescreening",
        "pre screening",
        "prescreen",
        "pre-screen",
        "screening report",
        "screening memo",
        "screening note",
        "initial screening",
        "deal screening",
        # initial review language
        "initial review",
        "initial assessment",
        "initial analysis",
        "initial evaluation",
        "initial diligence",
        "first look",
        "first pass",
        "quick look",
        "snapshot",
        "flash report",
        # opportunity language
        "opportunity assessment",
        "opportunity review",
        "opportunity analysis",
        "opportunity overview",
        "opportunity summary",
        "deal sourcing",
        "sourced via",
        "inbound",
        "pipeline review",
        "pipeline addition",
        "new opportunity",
        # evaluation framework
        "evaluation criteria",
        "fit assessment",
        "fund thesis fit",
        "thesis alignment",
        "thesis fit",
        "strategic fit",
        "market fit",
        "product-market fit",
        "no major red flags",
        "red flags",
        "preliminary findings",
        # next steps typical of pre-screens
        "next steps",
        "partner meeting",
        "schedule call",
        "introductory call",
        "management meeting",
        "reference calls",
        "begin drafting term sheet",
        "pass at this time",
        "move to next stage",
        "advance to diligence",
        # signals in body
        "seeking series",
        "raising",
        "looking to raise",
        "founded in",
        "headquartered in",
        "year founded",
        "number of employees",
        "headcount",
    ],

    # ── Meeting Minutes ───────────────────────────────────────────────────────
    # Covers board meetings, IC calls, portfolio reviews, investor updates
    "meeting_minutes": [
        # explicit minutes language
        "meeting minutes",
        "minutes of meeting",
        "minutes of the meeting",
        "board minutes",
        "board meeting minutes",
        "ic minutes",
        "investment committee minutes",
        "committee minutes",
        "meeting notes",
        "call notes",
        "call recap",
        "meeting recap",
        "meeting summary",
        "session notes",
        # structural signals
        "attendees",
        "in attendance",
        "present:",
        "participants:",
        "quorum",
        "called to order",
        "agenda",
        "agenda items",
        "agenda item",
        "discussed",
        "discussion",
        "noted",
        "resolved",
        "resolution",
        "motion",
        "seconded",
        "voted",
        "approved",
        "tabled",
        "deferred",
        "carried unanimously",
        "action items",
        "action item",
        "follow-up items",
        "follow-up actions",
        "next steps",
        "owner",
        "due date",
        "accountable",
        # board/governance context
        "board of directors",
        "board members",
        "board observer",
        "observer",
        "independent director",
        "chairperson",
        "chair",
        "ceo update",
        "cfo update",
        "coo update",
        "management update",
        "quarterly review",
        "quarterly update",
        "q1 review",
        "q2 review",
        "q3 review",
        "q4 review",
        "annual review",
        "portfolio review",
        "investor update",
        "lp update",
        # typical minute content
        "cash runway",
        "hiring update",
        "product update",
        "sales update",
        "fundraising update",
        "financing update",
        "operating plan",
        "budget approved",
        "compensation",
        "equity grant",
        "option grant",
        "stock option",
        "409a",
    ],
}

VALID_TYPES = set(_KEYWORDS.keys())
_CONFIDENCE_THRESHOLD = 3  # minimum keyword hits to trust the heuristic (raised from 2 — larger dictionaries need higher bar to avoid false positives)


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
