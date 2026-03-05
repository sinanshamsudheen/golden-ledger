"""
ExtractFields pipeline integration — extracts structured deal fields
from vectorized documents and persists them in the deal_fields table.

Public interface
----------------
    extract_deal_fields(db, deal, ext_doc_ids) -> bool

    db           — active SQLAlchemy session (caller owns lifecycle)
    deal         — Deal ORM object; deal.investment_type must already be set
    ext_doc_ids  — list of external vectorizer doc IDs to extract from
                   (caller should exclude pitch_deck docs for best results)

Returns True on success, False if the call failed or investment_type is
not mapped to a known field set.

On each call the existing deal_fields rows for the deal are deleted and
replaced, so the set always reflects the latest document versions.
"""

import json
import logging
import time
from typing import Optional

import requests

from worker.field_definitions import FIELDS_BY_INVESTMENT_TYPE, FieldDef

logger = logging.getLogger("worker.field_extractor")

_MAX_HTTP_RETRIES = 3
_HTTP_RETRY_BACKOFF = (5.0, 15.0, 30.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg():
    from app.config import settings
    return settings


def _headers() -> dict[str, str]:
    s = _cfg()
    key = s.RAG_FUNCTION_KEY or s.VECTORIZER_FUNCTION_KEY or ""
    return {"x-functions-key": key, "Content-Type": "application/json"}


def _retried_post(url: str, body: dict, timeout: int = 300) -> Optional[dict]:
    """POST with retries; returns parsed JSON dict or None on failure."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_HTTP_RETRIES + 2):
        try:
            resp = requests.post(url, headers=_headers(), json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt <= _MAX_HTTP_RETRIES:
                wait = _HTTP_RETRY_BACKOFF[min(attempt - 1, len(_HTTP_RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"[field_extractor] POST attempt {attempt}/{_MAX_HTTP_RETRIES + 1} "
                    f"failed: {exc} — retrying in {wait:.0f}s"
                )
                time.sleep(wait)
    logger.error(f"[field_extractor] All retries exhausted: {last_exc}")
    return None


def _to_str(value) -> Optional[str]:
    """Normalise an extracted value to a plain string for DB storage."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    # numbers, dicts, lists, booleans → JSON text
    return json.dumps(value)


# ── Public entry point ────────────────────────────────────────────────────────

def extract_deal_fields(db, deal, ext_doc_ids: list[str]) -> bool:
    """
    Call POST /api/ExtractFields for the deal's investment_type,
    delete any existing deal_fields rows for this deal, and insert fresh ones.
    """
    from app.models.deal_field import DealField

    investment_type: Optional[str] = deal.investment_type
    field_defs: Optional[list[FieldDef]] = FIELDS_BY_INVESTMENT_TYPE.get(
        investment_type or ""
    )
    if not field_defs:
        logger.warning(
            f"[field_extractor] Deal {deal.id}: no field definitions for "
            f"investment_type={investment_type!r} — skipping"
        )
        return False

    if not ext_doc_ids:
        logger.warning(
            f"[field_extractor] Deal {deal.id}: no doc IDs to extract from — skipping"
        )
        return False

    s = _cfg()
    url = f"{s.VECTORIZER_ANALYTICAL_URL}/api/ExtractFields"

    # Build the fields payload — one entry per field definition
    fields_payload = [
        {
            "name": f["field_name"],
            "description": f["description"],
            "type": "string",
            "instructions": f["instructions"],
        }
        for f in field_defs
    ]

    body = {
        "tenant_id": s.VECTORIZER_TENANT_ID,
        "doc_ids": ext_doc_ids,
        "fields": fields_payload,
        "retrieval_config": {
            "top_k": 10,
            "search_strategy": "hybrid",
        },
    }

    logger.info(
        f"[field_extractor] Deal {deal.id} ({deal.name!r}): "
        f"extracting {len(field_defs)} field(s) from {len(ext_doc_ids)} doc(s) "
        f"[investment_type={investment_type!r}]"
    )

    data = _retried_post(url, body, timeout=300)
    if data is None:
        return False

    if data.get("status") != "OK":
        logger.error(
            f"[field_extractor] Deal {deal.id}: ExtractFields returned "
            f"status={data.get('status')!r}: {str(data)[:400]}"
        )
        return False

    # Build lookup by field name for O(1) access
    result_by_name: dict[str, dict] = {
        f.get("name", ""): f for f in data.get("fields", [])
    }

    # ── Delete + reinsert in one transaction ──────────────────────────────────
    db.query(DealField).filter(DealField.deal_id == deal.id).delete(
        synchronize_session="fetch"
    )

    null_count = 0
    for fdef in field_defs:
        fname = fdef["field_name"]
        result = result_by_name.get(fname, {})

        if result.get("error"):
            logger.warning(
                f"[field_extractor] Deal {deal.id}: field '{fname}' "
                f"error: {result['error']}"
            )

        raw_value = result.get("value")
        raw_formatted = result.get("value_formatted")

        value_str = _to_str(raw_value)
        # value_formatted falls back to value if the API didn't provide it
        formatted_str = _to_str(raw_formatted) if raw_formatted is not None else value_str

        if value_str is None:
            null_count += 1

        db.add(
            DealField(
                deal_id=deal.id,
                field_name=fname,
                field_label=fdef["field_label"],
                field_type=fdef["field_type"],
                section=fdef["section"],
                value=value_str,
                value_formatted=formatted_str,
            )
        )

    db.commit()
    logger.info(
        f"[field_extractor] Deal {deal.id} ({deal.name!r}): "
        f"persisted {len(field_defs)} field(s) "
        f"({len(field_defs) - null_count} with values, {null_count} null)"
    )
    return True
