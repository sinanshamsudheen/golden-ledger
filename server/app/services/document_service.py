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
    Return the most recent document per doc_type for a given user.

    Uses a subquery that selects the maximum drive_created_time per doc_type,
    then joins back to retrieve the full document rows.
    Only includes documents with status 'processed' or 'vectorized'.
    """
    subquery = (
        db.query(
            Document.doc_type,
            func.max(Document.drive_created_time).label("max_date"),
        )
        .filter(
            Document.user_id == user_id,
            Document.status.in_(["processed", "vectorized"]),
            Document.doc_type.isnot(None),
        )
        .group_by(Document.doc_type)
        .subquery()
    )

    documents = (
        db.query(Document)
        .join(
            subquery,
            (Document.doc_type == subquery.c.doc_type)
            & (Document.drive_created_time == subquery.c.max_date),
        )
        .filter(Document.user_id == user_id)
        .all()
    )
    return documents
