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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from worker.classifier import VALID_TYPES

logger = logging.getLogger(__name__)

CHUNK_SIZE = 20          # docs per LLM call
TEXT_LIMIT = 1500        # chars of text sent per doc to LLM
_FALLBACK_TYPE = "pitch_deck"


@dataclass
class AnalysisResult:
    custom_id: str
    doc_type: str = _FALLBACK_TYPE
    deal_name: Optional[str] = None
    doc_date: Optional[datetime] = None
    summary: Optional[str] = None
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
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial analyst. Analyze investment documents and "
                        "return structured JSON only. No prose, no markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=100 * len(chunk),  # ~100 tokens per doc result
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        return _parse_response(raw, chunk)
    except Exception as exc:
        logger.error(f"Batch LLM call failed for chunk of {len(chunk)}: {exc}")
        return [_fallback_result(item) for item in chunk]


def _build_prompt(chunk: list[dict]) -> str:
    doc_types = ", ".join(VALID_TYPES)
    sections = []
    for item in chunk:
        excerpt = item["text"][:TEXT_LIMIT].replace("---", "- -")
        known = item.get("known_deal_name")
        hint = f" [deal hint: {known}]" if known else ""
        sections.append(
            f'--- {item["custom_id"]}: {item["file_name"]}{hint} ---\n{excerpt}'
        )

    docs_block = "\n\n".join(sections)
    return (
        f'Analyze these investment documents. Return ONLY a JSON object with key "results" '
        f"containing an array — one entry per document in the same order:\n"
        f'{{"results": [{{"custom_id":"...","doc_type":"...","deal_name":"...or null",'
        f'"doc_date":"YYYY-MM-DD or null","summary":"two sentence description"}},...]}}\n\n'
        f"Valid doc_type values: {doc_types}\n"
        f"For deal_name: if a [deal hint] is provided use it verbatim, otherwise extract "
        f"the company/deal name (max 3 words) from the document, or null if unclear.\n\n"
        f"{docs_block}"
    )


def _parse_response(raw: str, chunk: list[dict]) -> list[AnalysisResult]:
    try:
        data = json.loads(raw)
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
            )
        )
        logger.info(
            f"[batch] {item['file_name']}: type={doc_type} deal={deal_name} date={doc_date}"
        )

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _fallback_result(item: dict) -> AnalysisResult:
    return AnalysisResult(
        custom_id=item["custom_id"],
        doc_type=_FALLBACK_TYPE,
        from_heuristic=True,
    )
