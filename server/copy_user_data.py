"""
copy_user_data.py — Clone all deals, documents, and deal_fields from one user to another.

Usage (from the server/ directory):
    conda activate lokam
    python copy_user_data.py --from your@email.com --to tester@email.com

What it copies:
    deals       → new rows with target user_id (skips if deal name_key already exists)
    documents   → new rows with target user_id + updated deal_id
                  file_id is suffixed with _cp{target_user_id} to satisfy the unique constraint
                  (the tester won't have Drive access to the originals anyway)
    deal_fields → new rows pointing to the newly created deal IDs

Safe to re-run — already-copied deals are skipped, not duplicated.
"""

import sys
import argparse
from sqlalchemy.orm import Session

# Make sure we can import from app/
sys.path.insert(0, ".")
from app.database import SessionLocal
from app.models import User, Deal, Document, DealField


def copy_user_data(db: Session, from_email: str, to_email: str) -> None:
    src_user = db.query(User).filter(User.email == from_email).first()
    if not src_user:
        print(f"ERROR: source user '{from_email}' not found in the database.")
        return

    dst_user = db.query(User).filter(User.email == to_email).first()
    if not dst_user:
        print(f"ERROR: target user '{to_email}' not found in the database.")
        print("       Make sure they have logged in at least once so their account exists.")
        return

    print(f"\nSource : [{src_user.id}] {src_user.email}")
    print(f"Target : [{dst_user.id}] {dst_user.email}\n")

    src_deals = db.query(Deal).filter(Deal.user_id == src_user.id).all()
    print(f"Found {len(src_deals)} deals to copy.\n")

    deals_created = 0
    deals_skipped = 0
    docs_created = 0
    docs_skipped = 0
    fields_created = 0

    for src_deal in src_deals:
        # ── Deal ──────────────────────────────────────────────────────────────
        existing_deal = (
            db.query(Deal)
            .filter(Deal.user_id == dst_user.id, Deal.name_key == src_deal.name_key)
            .first()
        )

        if existing_deal:
            dst_deal = existing_deal
            print(f"  [SKIP deal] '{src_deal.name}' already exists for target user")
            deals_skipped += 1
        else:
            dst_deal = Deal(
                user_id=dst_user.id,
                name=src_deal.name,
                name_key=src_deal.name_key,
                investment_type=src_deal.investment_type,
                deal_status=src_deal.deal_status,
                deal_reason=src_deal.deal_reason,
                vectorizer_job_id=src_deal.vectorizer_job_id,
            )
            db.add(dst_deal)
            db.flush()  # get dst_deal.id without committing
            print(f"  [NEW  deal] '{src_deal.name}' → id={dst_deal.id}")
            deals_created += 1

        # ── Documents ─────────────────────────────────────────────────────────
        src_docs = (
            db.query(Document).filter(Document.deal_id == src_deal.id).all()
        )

        old_doc_to_new: dict[int, int] = {}  # src doc id → dst doc id (for future use)

        for src_doc in src_docs:
            # Use the real Drive file_id — now safe because file_id is unique
            # per-user (migration 0008), so two users can hold the same file_id.
            new_file_id = src_doc.file_id

            already = (
                db.query(Document)
                .filter(Document.user_id == dst_user.id, Document.file_id == new_file_id)
                .first()
            )
            if already:
                docs_skipped += 1
                old_doc_to_new[src_doc.id] = already.id
                continue

            dst_doc = Document(
                user_id=dst_user.id,
                file_id=new_file_id,
                file_name=src_doc.file_name,
                file_path=src_doc.file_path,
                doc_type=src_doc.doc_type,
                description=src_doc.description,
                doc_created_date=src_doc.doc_created_date,
                drive_created_time=src_doc.drive_created_time,
                checksum=src_doc.checksum,
                status=src_doc.status,
                deal_id=dst_deal.id,
                folder_path=src_doc.folder_path,
                version_status=src_doc.version_status,
                vectorizer_doc_id=src_doc.vectorizer_doc_id,
            )
            db.add(dst_doc)
            db.flush()
            old_doc_to_new[src_doc.id] = dst_doc.id
            docs_created += 1

        # ── Deal fields ───────────────────────────────────────────────────────
        # Only copy fields if we just created the deal (skip if deal already existed)
        if not existing_deal:
            src_fields = (
                db.query(DealField).filter(DealField.deal_id == src_deal.id).all()
            )
            for src_field in src_fields:
                dst_field = DealField(
                    deal_id=dst_deal.id,
                    field_name=src_field.field_name,
                    field_label=src_field.field_label,
                    field_type=src_field.field_type,
                    section=src_field.section,
                    value=src_field.value,
                    value_formatted=src_field.value_formatted,
                )
                db.add(dst_field)
                fields_created += 1

    db.commit()

    print(f"\n{'─'*50}")
    print(f"Done.")
    print(f"  Deals   : {deals_created} created, {deals_skipped} skipped (already existed)")
    print(f"  Docs    : {docs_created} created, {docs_skipped} skipped (already copied)")
    print(f"  Fields  : {fields_created} created")
    print(f"{'─'*50}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy all deals/docs/fields from one user to another.")
    parser.add_argument("--from", dest="from_email", required=True, help="Source user email")
    parser.add_argument("--to",   dest="to_email",   required=True, help="Target user email")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        copy_user_data(db, args.from_email, args.to_email)
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
