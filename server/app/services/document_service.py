import logging
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.document import Document
from ..schemas.document_schema import DocumentCreate

logger = logging.getLogger(__name__)


def get_document_by_file_id(db: Session, file_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.file_id == file_id).first()


def get_document_by_checksum(db: Session, user_id: int, checksum: str) -> Optional[Document]:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.checksum == checksum)
        .first()
    )


def create_document(db: Session, doc_data: DocumentCreate) -> Document:
    document = Document(**doc_data.model_dump())
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def update_document(db: Session, document_id: int, **kwargs) -> Optional[Document]:
    """Update arbitrary fields on a document record."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        return None
    for key, value in kwargs.items():
        if hasattr(document, key):
            setattr(document, key, value)
    db.commit()
    db.refresh(document)
    return document


def get_latest_documents_per_type(db: Session, user_id: int) -> List[Document]:
    """
    Return the most recent document per (deal_id, doc_type) for a given user.

    Groups by deal so each deal's latest pitch_deck, investment_memo etc. is
    returned independently — not just the single globally newest per type.

    Dealless documents (deal_id IS NULL) are grouped by (folder_path, doc_type)
    so misc/ files also contribute their latest version.

    Only includes documents with status 'processed' or 'vectorized'.
    """
    # ── Deal-scoped: latest per (deal_id, doc_type) ───────────────────────────
    deal_subq = (
        db.query(
            Document.deal_id,
            Document.doc_type,
            func.max(Document.drive_created_time).label("max_date"),
        )
        .filter(
            Document.user_id == user_id,
            Document.status.in_(["processed", "vectorized"]),
            Document.doc_type.isnot(None),
            Document.deal_id.isnot(None),
        )
        .group_by(Document.deal_id, Document.doc_type)
        .subquery()
    )

    deal_docs = (
        db.query(Document)
        .join(
            deal_subq,
            (Document.deal_id == deal_subq.c.deal_id)
            & (Document.doc_type == deal_subq.c.doc_type)
            & (Document.drive_created_time == deal_subq.c.max_date),
        )
        .filter(Document.user_id == user_id)
        .all()
    )

    # ── Dealless: latest per (folder_path, doc_type) ──────────────────────────
    folder_subq = (
        db.query(
            Document.folder_path,
            Document.doc_type,
            func.max(Document.drive_created_time).label("max_date"),
        )
        .filter(
            Document.user_id == user_id,
            Document.status.in_(["processed", "vectorized"]),
            Document.doc_type.isnot(None),
            Document.deal_id.is_(None),
        )
        .group_by(Document.folder_path, Document.doc_type)
        .subquery()
    )

    folder_docs = (
        db.query(Document)
        .join(
            folder_subq,
            (Document.folder_path == folder_subq.c.folder_path)
            & (Document.doc_type == folder_subq.c.doc_type)
            & (Document.drive_created_time == folder_subq.c.max_date),
        )
        .filter(Document.user_id == user_id, Document.deal_id.is_(None))
        .all()
    )

    return deal_docs + folder_docs
