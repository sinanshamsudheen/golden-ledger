import logging
from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models.user import User
from ..models.document import Document
from ..models.deal import Deal
from ..services.document_service import get_latest_documents_per_type
from ..schemas.document_schema import (
    LatestDocumentResponse,
    AllDocumentResponse,
    DealResponse,
    DealDocSlots,
    DealDocSlot,
    ArchivedDoc,
)
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
limiter = Limiter(key_func=get_remote_address)

_DOC_TYPES = ["pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes"]


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
) -> List[AllDocumentResponse]:
    """Return all processed documents for the current user."""
    docs = (
        db.query(Document)
        .filter(
            Document.user_id == current_user.id,
            Document.status.in_(["processed", "vectorized"]),
        )
        .order_by(Document.created_at.desc())
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
) -> List[DealResponse]:
    """
    Return all deals for the current user, each with:
    - documents: the 4 canonical type slots (current versions only)
    - archived: superseded documents
    """
    deals = (
        db.query(Deal)
        .filter(Deal.user_id == current_user.id)
        .order_by(Deal.name)
        .all()
    )

    result: list[DealResponse] = []
    for deal in deals:
        docs = (
            db.query(Document)
            .filter(
                Document.deal_id == deal.id,
                Document.status.in_(["processed", "vectorized"]),
            )
            .all()
        )

        # Fill the 4 current slots (latest doc per type)
        slots: dict[str, DealDocSlot | None] = {t: None for t in _DOC_TYPES}
        archived: list[ArchivedDoc] = []

        # Track current docs per type for slot filling (keep newest by doc_created_date)
        current_by_type: dict[str, Document] = {}
        for doc in docs:
            dtype = doc.doc_type or ""
            if doc.version_status == "superseded":
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

    docs = (
        db.query(Document)
        .filter(
            Document.deal_id == deal.id,
            Document.status.in_(["processed", "vectorized"]),
        )
        .all()
    )

    slots: dict[str, DealDocSlot | None] = {t: None for t in _DOC_TYPES}
    archived: list[ArchivedDoc] = []

    current_by_type: dict[str, Document] = {}
    for doc in docs:
        dtype = doc.doc_type or ""
        if doc.version_status == "superseded":
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
    return DealResponse(
        id=deal.id,
        name=deal.name,
        documents=DealDocSlots(**slots),
        archived=archived,
        doc_count=doc_count,
        investment_type=deal.investment_type,
        deal_status=deal.deal_status,
        deal_reason=deal.deal_reason,
    )
