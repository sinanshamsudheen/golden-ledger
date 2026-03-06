import logging
from typing import List  # noqa: UP035

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models.user import User
from ..models.document import Document
from ..models.deal import Deal
from ..models.deal_field import DealField
from ..services.document_service import get_latest_documents_per_type
from ..schemas.document_schema import (
    LatestDocumentResponse,
    AllDocumentResponse,
    DealResponse,
    DealDocSlots,
    DealDocSlot,
    ArchivedDoc,
    LockedFileDoc,
    LockedFileWithDeal,
    DealFieldResponse,
)
from ..utils.auth import get_current_user
from ..constants import DOC_TYPES as _DOC_TYPES, PIPELINE_TYPES as _PIPELINE_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
limiter = Limiter(key_func=get_remote_address)


def _is_minutes_only(current_by_type: dict) -> bool:
    """Return True if the deal has no pipeline-relevant document types."""
    return not any(t in _PIPELINE_TYPES for t in current_by_type)


def _fmt_date(dt) -> str | None:
    return dt.strftime("%Y-%m-%d") if dt else None


@router.get("/latest", response_model=List[LatestDocumentResponse])
@limiter.limit("60/minute")
def latest_documents(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[LatestDocumentResponse]:
    """Return the latest processed document per document type for the current user."""
    documents = get_latest_documents_per_type(db, current_user.id)
    return [
        LatestDocumentResponse(
            type=doc.doc_type or "pitch_deck",
            name=doc.file_name,
            date=_fmt_date(doc.doc_created_date),
            description=doc.description,
        )
        for doc in documents
    ]


@router.get("/all", response_model=List[AllDocumentResponse])
@limiter.limit("60/minute")
def all_documents(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=2000, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> List[AllDocumentResponse]:
    """Return processed documents for the current user (paginated, default 2000)."""
    docs = (
        db.query(Document)
        .filter(
            Document.user_id == current_user.id,
            Document.status.in_(["processed", "vectorized"]),
        )
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        AllDocumentResponse(
            id=doc.id,
            file_id=doc.file_id,
            type=doc.doc_type or "pitch_deck",
            name=doc.file_name,
            date=_fmt_date(doc.doc_created_date),
            description=doc.description,
            status=doc.status,
            deal_id=doc.deal_id,
            deal_name=doc.deal.name if doc.deal else None,
            version_status=doc.version_status or "current",
            folder_path=doc.folder_path,
        )
        for doc in docs
    ]


@router.get("/deals", response_model=List[DealResponse])
@limiter.limit("60/minute")
def list_deals(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> List[DealResponse]:
    """
    Return deals for the current user (paginated, default 1000), each with:
    - documents: the 4 canonical type slots (current versions only)
    - archived: superseded documents
    """
    deals = (
        db.query(Deal)
        .filter(Deal.user_id == current_user.id)
        .order_by(Deal.name)
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Batch-load all deal_fields in one query (avoids N+1)
    deal_ids = [d.id for d in deals]
    all_deal_field_rows = (
        db.query(DealField)
        .filter(DealField.deal_id.in_(deal_ids))
        .order_by(DealField.id)
        .all()
    ) if deal_ids else []
    fields_by_deal: dict[int, list[DealField]] = {}
    for f in all_deal_field_rows:
        fields_by_deal.setdefault(f.deal_id, []).append(f)

    result: list[DealResponse] = []
    for deal in deals:
        # Hide deals that went through the full pipeline but couldn't be classified
        if deal.vectorizer_job_id is not None and deal.investment_type is None:
            continue

        docs = (
            db.query(Document)
            .filter(
                Document.deal_id == deal.id,
                Document.doc_type.in_(_DOC_TYPES + ["password_protected"]),
                Document.status.in_(["processed", "vectorized", "skipped"]),
            )
            .all()
        )

        # Fill the 4 current slots (latest doc per type)
        slots: dict[str, DealDocSlot | None] = {t: None for t in _DOC_TYPES}
        archived: list[ArchivedDoc] = []
        locked: list[LockedFileDoc] = []

        # Track current docs per type for slot filling (keep newest by doc_created_date)
        current_by_type: dict[str, Document] = {}
        for doc in docs:
            dtype = doc.doc_type or ""
            if dtype == "password_protected":
                locked.append(
                    LockedFileDoc(
                        id=doc.id,
                        file_id=doc.file_id,
                        name=doc.file_name,
                        date=_fmt_date(doc.doc_created_date or doc.drive_created_time),
                    )
                )
            elif doc.version_status == "superseded":
                archived.append(
                    ArchivedDoc(
                        id=doc.id,
                        file_id=doc.file_id,
                        type=dtype,
                        name=doc.file_name,
                        date=_fmt_date(doc.doc_created_date),
                    )
                )
            elif dtype in slots:
                existing = current_by_type.get(dtype)
                if existing is None or (
                    doc.doc_created_date
                    and (
                        existing.doc_created_date is None
                        or doc.doc_created_date >= existing.doc_created_date
                    )
                ):
                    current_by_type[dtype] = doc

        for dtype, doc in current_by_type.items():
            slots[dtype] = DealDocSlot(
                id=doc.id,
                file_id=doc.file_id,
                name=doc.file_name,
                date=_fmt_date(doc.doc_created_date),
                description=doc.description,
                vectorizer_doc_id=doc.vectorizer_doc_id,
            )

        doc_count = sum(1 for v in slots.values() if v is not None)

        # Skip client/portfolio deals that only have meeting minutes
        if _is_minutes_only(current_by_type):
            continue

        deal_fields = [
            DealFieldResponse(
                field_name=f.field_name,
                field_label=f.field_label,
                field_type=f.field_type,
                section=f.section,
                value=f.value,
                value_formatted=f.value_formatted,
            )
            for f in fields_by_deal.get(deal.id, [])
        ]

        result.append(
            DealResponse(
                id=deal.id,
                name=deal.name,
                documents=DealDocSlots(**slots),
                archived=archived,
                doc_count=doc_count,
                investment_type=deal.investment_type,
                deal_status=deal.deal_status,
                deal_reason=deal.deal_reason,
                deal_fields=deal_fields,
                locked_files=locked,
            )
        )

    return result


@router.get("/deals/{deal_id}", response_model=DealResponse)
@limiter.limit("60/minute")
def get_deal(
    deal_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DealResponse:
    """Return a single deal with its documents and archive."""
    from fastapi import HTTPException

    deal = (
        db.query(Deal)
        .filter(Deal.id == deal_id, Deal.user_id == current_user.id)
        .first()
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Hide deals that went through the full pipeline but couldn't be classified
    if deal.vectorizer_job_id is not None and deal.investment_type is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    docs = (
        db.query(Document)
        .filter(
            Document.deal_id == deal.id,
            Document.doc_type.in_(_DOC_TYPES + ["password_protected"]),
            Document.status.in_(["processed", "vectorized", "skipped"]),
        )
        .all()
    )

    slots: dict[str, DealDocSlot | None] = {t: None for t in _DOC_TYPES}
    archived: list[ArchivedDoc] = []
    locked: list[LockedFileDoc] = []

    current_by_type: dict[str, Document] = {}
    for doc in docs:
        dtype = doc.doc_type or ""
        if dtype == "password_protected":
            locked.append(
                LockedFileDoc(
                    id=doc.id,
                    file_id=doc.file_id,
                    name=doc.file_name,
                    date=_fmt_date(doc.doc_created_date or doc.drive_created_time),
                )
            )
        elif doc.version_status == "superseded":
            archived.append(
                ArchivedDoc(
                    id=doc.id,
                    file_id=doc.file_id,
                    type=dtype,
                    name=doc.file_name,
                    date=_fmt_date(doc.doc_created_date),
                )
            )
        elif dtype in slots:
            existing = current_by_type.get(dtype)
            if existing is None or (
                doc.doc_created_date
                and (
                    existing.doc_created_date is None
                    or doc.doc_created_date >= existing.doc_created_date
                )
            ):
                current_by_type[dtype] = doc

    for dtype, doc in current_by_type.items():
        slots[dtype] = DealDocSlot(
            id=doc.id,
            file_id=doc.file_id,
            name=doc.file_name,
            date=_fmt_date(doc.doc_created_date),
            description=doc.description,
            vectorizer_doc_id=doc.vectorizer_doc_id,
        )

    doc_count = sum(1 for v in slots.values() if v is not None)

    if _is_minutes_only(current_by_type):
        raise HTTPException(status_code=404, detail="Deal not found")

    deal_fields = [
        DealFieldResponse(
            field_name=f.field_name,
            field_label=f.field_label,
            field_type=f.field_type,
            section=f.section,
            value=f.value,
            value_formatted=f.value_formatted,
        )
        for f in (
            db.query(DealField)
            .filter(DealField.deal_id == deal.id)
            .order_by(DealField.id)
            .all()
        )
    ]

    return DealResponse(
        id=deal.id,
        name=deal.name,
        documents=DealDocSlots(**slots),
        archived=archived,
        doc_count=doc_count,
        investment_type=deal.investment_type,
        deal_status=deal.deal_status,
        deal_reason=deal.deal_reason,
        deal_fields=deal_fields,
        locked_files=locked,
    )


@router.get("/locked", response_model=List[LockedFileWithDeal])
@limiter.limit("60/minute")
def locked_files(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=2000, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> List[LockedFileWithDeal]:
    """Return password-protected files for the current user (paginated, default 2000)."""
    docs = (
        db.query(Document)
        .filter(
            Document.user_id == current_user.id,
            Document.doc_type == "password_protected",
        )
        .order_by(Document.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Batch-load all referenced deals in one query (avoids N+1)
    deal_ids_needed = {doc.deal_id for doc in docs if doc.deal_id}
    deals_by_id: dict[int, Deal] = {}
    if deal_ids_needed:
        deals_by_id = {
            d.id: d
            for d in db.query(Deal).filter(Deal.id.in_(deal_ids_needed)).all()
        }

    # Deduplicate by file_id (same file can appear in multiple sub-folders)
    seen: set[str] = set()
    result: list[LockedFileWithDeal] = []
    for doc in docs:
        if doc.file_id in seen:
            continue
        seen.add(doc.file_id)
        deal = deals_by_id.get(doc.deal_id) if doc.deal_id else None
        result.append(
            LockedFileWithDeal(
                id=doc.id,
                file_id=doc.file_id,
                name=doc.file_name,
                date=_fmt_date(doc.doc_created_date),
                deal_id=doc.deal_id,
                deal_name=deal.name if deal else None,
            )
        )
    return result
