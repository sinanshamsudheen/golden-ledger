"""
Multi-document batch analyzer.

Groups up to CHUNK_SIZE documents into a single OpenAI call that returns a
JSON array with doc_type, deal_name, doc_date, and summary for every document.

This replaces three separate per-document LLM calls (classify, deal_name,
summarize) with roughly N/CHUNK_SIZE calls total — ~20x fewer API calls for a
typical 200-file run.

Public interface
----------------
analyze_batch(items) -> list[AnalysisResult]

  items  : list of {"custom_id": str, "file_name": str, "text": str}
  returns: one AnalysisResult per item in the same order
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

VALID_TYPES = {"pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes", "other"}

logger = logging.getLogger(__name__)

_MAX_LLM_RETRIES = 3
_LLM_RETRY_BACKOFF = (5.0, 15.0, 30.0)   # wait (seconds) before attempt n+1

CHUNK_SIZE = 20          # docs per LLM call
TEXT_LIMIT = 1500        # chars of text sent per doc to LLM
_FALLBACK_TYPE = "pitch_deck"

# ── Output schema (shown verbatim to the model) ───────────────────────────────
OUTPUT_SCHEMA = """
{
  "results": [
    {
      "custom_id": "<exact custom_id from input>",
      "is_client": "<true if existing portfolio/client file, false if new deal/opportunity being evaluated>",
      "doc_type": "<one of: pitch_deck | investment_memo | prescreening_report | meeting_minutes | other>",
      "deal_name": "<company or deal name, max 3 words, or null>",
      "doc_date": "<YYYY-MM-DD or null>",
      "summary": "<two sentence description of the document>"
    }
  ]
}
"""


@dataclass
class AnalysisResult:
    custom_id: str
    doc_type: str = _FALLBACK_TYPE
    deal_name: Optional[str] = None
    doc_date: Optional[datetime] = None
    summary: Optional[str] = None
    is_client: bool = False
    from_heuristic: bool = False


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_batch(
    items: list[dict],
) -> list[AnalysisResult]:
    """
    Analyze a list of documents.  Each item must have keys:
        custom_id, file_name, text

    Returns one AnalysisResult per item in the same order.
    """
    if not items:
        return []

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — using fallback for all documents")
        return [_fallback_result(item) for item in items]

    chunks = [items[i : i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)]

    # Run all chunk calls in parallel — each is an independent HTTP request
    chunk_results_map: dict[int, list[AnalysisResult]] = {}
    with ThreadPoolExecutor(max_workers=min(len(chunks), 10)) as pool:
        futures = {pool.submit(_analyze_chunk, chunk, api_key): idx for idx, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                chunk_results_map[idx] = future.result()
            except Exception as exc:
                logger.error(f"Chunk {idx} raised unexpectedly: {exc}")
                chunk_results_map[idx] = [_fallback_result(item) for item in chunks[idx]]

    results: list[AnalysisResult] = []
    for idx in range(len(chunks)):
        results.extend(chunk_results_map[idx])

    return results


# ── Chunk processing ──────────────────────────────────────────────────────────

def _analyze_chunk(chunk: list[dict], api_key: str) -> list[AnalysisResult]:
    prompt = _build_prompt(chunk)
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial analyst assistant. "
                        "You MUST respond with a single valid JSON object that strictly follows "
                        "the output schema provided in the user message. "
                        "No markdown, no code fences, no prose — raw JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=400 * len(chunk),  # ~400 tokens per doc result
        )
        raw = response.choices[0].message.content or ""
        if not raw.strip():
            logger.error(
                f"Empty content from LLM for chunk of {len(chunk)} — "
                f"finish_reason={response.choices[0].finish_reason}"
            )
            return [_fallback_result(item) for item in chunk]
        logger.debug(f"LLM raw response (first 200 chars): {raw[:200]}")
        return _parse_response(raw, chunk)
    except Exception as exc:
        logger.error(f"Batch LLM call failed for chunk of {len(chunk)}: {exc}")
        return [_fallback_result(item) for item in chunk]


def _build_prompt(chunk: list[dict]) -> str:
    sections = []
    for item in chunk:
        excerpt = item["text"][:TEXT_LIMIT].replace("---", "- -")
        folder = item.get("folder_path", "").strip()
        location = f" [folder: {folder}]" if folder else ""
        sections.append(
            f'--- {item["custom_id"]}: {item["file_name"]}{location} ---\n{excerpt}'
        )
    docs_block = "\n\n".join(sections)
    valid_types_str = " | ".join(sorted(VALID_TYPES))

    prompt = f"""\
You are a senior financial analyst at a venture capital firm specializing in deal document intelligence.

PRIMARY OBJECTIVE: Analyze a batch of investment documents and extract structured metadata \
for each one — doc_type, deal_name, doc_date, and a two-sentence summary.

## PART 1: OUTPUT SCHEMA

Return a single JSON object with one entry in `results` per document, \
in the same order as the input.

{OUTPUT_SCHEMA.strip()}

## PART 2: FIELD RULES

### `custom_id`
- Copy exactly from the document header: `--- <custom_id>: filename ---`
- Do not modify, truncate, or infer.

### `is_client`
Set to `true` if this document belongs to an **existing portfolio company / current client** \
(a company the fund already manages or has already invested in), NOT a new deal being evaluated.

Signals → `true` (existing client/portfolio):
- Quarterly/annual report, board update, or investor update *from* a portfolio company
- Folder path contains words like "Portfolio", "Clients", "Current Investments", "Post-Investment", "Active"
- Operational report, cap table update, or company financials sent *to* investors (no fundraising ask)
- Governance documents, AGM minutes, or shareholder letters for an already-invested company

Signals → `false` (new deal / opportunity being evaluated):
- Fundraising ask, pitch deck, term sheet, or investment memo for evaluation
- Prescreening or first-look of a company seeking capital
- IC meeting minutes discussing *whether* to invest in a new company (formal committee session, not a call recap)
- Data room materials from an external company seeking investment

**When in doubt, default to `false`** (assume deal/opportunity).

### `doc_type`
Apply in strict order (stop at the first match):

[T1] MEETING MINUTES — IC/Investment Committee only
- MUST be a formal Investment Committee (IC) session where a deal is deliberated or voted on.
- Strong signals: "Investment Committee", "IC minutes", "IC meeting", "committee resolution",
  "investment approved", "investment rejected", "proceed with investment", "pass on deal",
  "IC recommendation", "voted to invest", "motion carried", "quorum"
- The document must record a formal DECISION process — not just discussion or an update.

EXCLUDE from `meeting_minutes` — classify as `other` instead:
- Call notes, call recap, catch-up notes, intro call, exploratory call, reference call
- Due diligence calls, DD call notes, founder call notes
- Board updates, management updates, LP updates, quarterly/annual reviews
- Any meeting that is informational or operational (no investment vote/resolution)
→ `meeting_minutes`

[T2] PRESCREENING REPORT
- Contains: initial assessment, first look, deal screening, opportunity overview, \
"next steps: schedule partner meeting", fund thesis fit
→ `prescreening_report`

[T3] INVESTMENT MEMO
- Contains: financial analysis, due diligence, term sheet, investment recommendation, \
ARR/MRR, unit economics, LTV/CAC, burn rate, cap table, deal memo
→ `investment_memo`

[T4] PITCH DECK
- Contains: company overview, funding ask, go-to-market, product pitch, \
market size, founding team, use of proceeds
→ `pitch_deck`

DEFAULT: If none match → `other`

Must be exactly one of: `{valid_types_str}`

### `deal_name`
- Extract from **document content first** — folder path is supporting context only.
- Return the shortest unambiguous name (max 3 words). Strip legal suffixes (Inc, Ltd, LLC, Corp).
- Return `null` if the deal name cannot be determined with confidence.

### `doc_date`
- Find the date the document was **authored or published** — not dates referenced in the body.
- Scan: `Date:` headers, title pages, opening paragraph, footers.
- Normalize any format to `YYYY-MM-DD` (e.g. "April 4th, 2024" → "2024-04-04").
- Return `null` **only** if no date appears anywhere in the text.

### `summary`
- Exactly **two sentences**.
- Sentence 1: what the document is and who/what it concerns.
- Sentence 2: the single most important insight, metric, decision, or next step.
- Be specific — include numbers, names, outcomes where available.
- Do not begin with "This document".

## PART 3: DOCUMENTS TO ANALYZE

{docs_block}

## FEW-SHOT EXAMPLES

### Ex 1: Pitch Deck — explicit date header
**Input excerpt**:
Date: 2023-09-26
Acme Robotics - Series A Investor Presentation
We are building autonomous warehouse robots...

**Output entry**:
{{
  "custom_id": "abc123",
  "doc_type": "pitch_deck",
  "deal_name": "Acme Robotics",
  "doc_date": "2023-09-26",
  "summary": "Acme Robotics is seeking Series A funding to scale its autonomous warehouse robotics platform. The deck covers market opportunity, product overview, and financial projections."
}}

### Ex 2: IC Meeting Minutes — formal investment committee session
**Input excerpt**:
Investment Committee Meeting Minutes
Date: October 2, 2023
Attendees: David Park (Managing Partner, Chair), Emily Watson (Partner), Robert Kim (Associate)
Agenda: IC vote on Beta Health Series A investment
Discussion: Committee reviewed prescreening report and investment memo. Emily raised concerns about customer concentration risk. David noted strong ARR growth of 180% YoY. Motion to proceed with $3M lead investment at $22M cap.
Resolution: Carried unanimously. Proceed to term sheet.
Action items: Legal to prepare term sheet by Oct 9.

**Output entry**:
{{
  "custom_id": "def456",
  "doc_type": "meeting_minutes",
  "deal_name": "Beta Health",
  "doc_date": "2023-10-02",
  "summary": "Investment Committee minutes for the Beta Health Series A vote, chaired by David Park with Emily Watson and Robert Kim in attendance. The committee unanimously approved a $3M lead investment at a $22M cap, with a term sheet to be issued by October 9."
}}
**Why**: Explicit "Investment Committee", "motion", "resolution", "carried unanimously" — formal IC decision session, not a call recap or board update.

### Ex 3: Investment Memo — no explicit deal name in body, folder as fallback
**Input excerpt** [folder: Portfolio/Gamma Fintech/]:
Financial Summary
Total ARR: $2.8M as of Q4 2024. Gross Margin: 76%. Monthly Burn: $180K.

**Output entry**:
{{
  "custom_id": "ghi789",
  "doc_type": "investment_memo",
  "deal_name": "Gamma Fintech",
  "doc_date": null,
  "summary": "Financial summary for Gamma Fintech reporting $2.8M ARR with 76% gross margin and $180K monthly burn. The document highlights improving unit economics and an 18-month cash runway."
}}

### Ex 4: Prescreening Report — date in natural language, no folder context
**Input excerpt**:
Initial Assessment: Zeta Energy
Date: April 4th, 2024
This first look covers Zeta Energy, a clean energy startup seeking seed funding...

**Output entry**:
{{
  "custom_id": "jkl012",
  "doc_type": "prescreening_report",
  "deal_name": "Zeta Energy",
  "doc_date": "2024-04-04",
  "summary": "Initial prescreening assessment of Zeta Energy, a clean energy startup seeking seed investment. The report finds no major red flags and recommends scheduling a partner meeting."
}}

### Ex 5: Ambiguous doc — reasoning through type signals
**Input excerpt**:
Due Diligence Checklist - Gamma Fintech
Corporate Documents: Certificate of incorporation, cap table, board consents...
Financial Information: Historical financials, budget, tax returns, debt schedules...

**Output entry**:
{{
  "custom_id": "mno345",
  "doc_type": "investment_memo",
  "deal_name": "Gamma Fintech",
  "doc_date": null,
  "summary": "Due diligence checklist for the Gamma Fintech transaction outlining required corporate and financial documentation. The document requests cap table, historical financials, IP portfolio, and legal compliance records by end of week."
}}
**Why**: Contains "due diligence", "cap table", "debt schedules" → matches [T3] investment_memo before reaching [T4].

### Ex 6: Call notes — NOT meeting_minutes
**Input excerpt**:
Call Notes — Beta Health Intro Call
Date: September 15, 2023
Attendees: David Park (GP), Sarah Chen (CEO, Beta Health)
Topics: Company overview, market opportunity, funding timeline
Notes: Sarah walked through the pitch. Team of 8, $1.2M ARR, raising Series A at $18-22M cap.
Next steps: Share data room access, follow-up call in two weeks.

**Output entry**:
{{
  "custom_id": "pqr678",
  "doc_type": "other",
  "deal_name": "Beta Health",
  "doc_date": "2023-09-15",
  "summary": "Introductory call notes between GP David Park and Beta Health CEO Sarah Chen covering company overview and Series A fundraising. Next steps include data room access and a follow-up call in two weeks."
}}
**Why**: "Call Notes", "intro call", "next steps: follow-up call" — this is a call recap, not a formal IC decision session. Must be `other`, never `meeting_minutes`.

---
"""

    return prompt


def _parse_response(raw: str, chunk: list[dict]) -> list[AnalysisResult]:
    # Strip markdown code fences if model wraps the JSON
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(stripped)
        entries = data.get("results", [])
        if not isinstance(entries, list):
            raise ValueError("'results' is not a list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(f"Failed to parse LLM JSON response: {exc}\nRaw: {raw[:500]}")
        return [_fallback_result(item) for item in chunk]

    # Build lookup by custom_id, fall back to positional if id is missing
    by_id: dict[str, dict] = {}
    for i, entry in enumerate(entries):
        cid = entry.get("custom_id") or chunk[i]["custom_id"] if i < len(chunk) else None
        if cid:
            by_id[cid] = entry

    results = []
    for item in chunk:
        entry = by_id.get(item["custom_id"])
        if not entry:
            results.append(_fallback_result(item))
            continue

        doc_type = entry.get("doc_type", "").strip().lower()
        if doc_type not in VALID_TYPES:
            doc_type = _FALLBACK_TYPE

        is_client = bool(entry.get("is_client", False))

        deal_name = entry.get("deal_name") or None
        if deal_name:
            deal_name = deal_name.strip() or None

        doc_date = _parse_date(entry.get("doc_date"))
        summary = entry.get("summary") or None

        results.append(
            AnalysisResult(
                custom_id=item["custom_id"],
                doc_type=doc_type,
                deal_name=deal_name,
                doc_date=doc_date,
                summary=summary,
                is_client=is_client,
            )
        )
        logger.info(
            f"[batch] {item['file_name']}: type={doc_type} deal={deal_name} date={doc_date} is_client={is_client}"
        )

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse a date string returned by the LLM into a datetime.

    The LLM is instructed to return YYYY-MM-DD but may occasionally return
    other formats. Try a broad set of patterns before giving up.
    """
    if not raw:
        return None
    value = raw.strip()
    _FORMATS = [
        "%Y-%m-%d",       # 2024-03-15  (primary — LLM instructed)
        "%d-%m-%Y",       # 15-03-2024
        "%m/%d/%Y",       # 03/15/2024
        "%d/%m/%Y",       # 15/03/2024
        "%Y/%m/%d",       # 2024/03/15
        "%B %d, %Y",      # March 15, 2024
        "%b %d, %Y",      # Mar 15, 2024
        "%d %B %Y",       # 15 March 2024
        "%d %b %Y",       # 15 Mar 2024
        "%B %Y",          # March 2024  → treated as 1st of month
        "%b %Y",          # Mar 2024
        "%Y-%m",          # 2024-03
        "%Y",             # 2024        → treated as Jan 1
    ]
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.warning(f"Could not parse doc_date '{value}' with any known format")
    return None


def _fallback_result(item: dict) -> AnalysisResult:
    return AnalysisResult(
        custom_id=item["custom_id"],
        doc_type=_FALLBACK_TYPE,
        from_heuristic=True,
    )
