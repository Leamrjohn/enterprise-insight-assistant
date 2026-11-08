"""Register an already-ingested document as a version; retires the one it replaces.

Validity comes from the person registering the document, never from its date
header: those headers are report dates and are often not the validity period.

Run:
    python -m scripts.ops.register_document_version --company-id 1 --document-id 7 \
        --group travel-policy --version 2 --effective-from 2025-01-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from app.db.session import SessionLocal, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.documents.models import Documents
from app.modules.documents.versioning import register_document_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--document-id", type=int, required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--effective-from", type=date.fromisoformat, required=True)
    parser.add_argument("--effective-to", type=date.fromisoformat)
    parser.add_argument("--kind")
    parser.add_argument("--applies-to")
    args = parser.parse_args()

    with SessionLocal() as db:
        set_tenant_scope(db, args.company_id)
        document = db.get(Documents, args.document_id)
        if document is None or document.company_id != args.company_id:
            sys.exit("document not found in this company")
        register_document_version(
            db,
            document=document,
            version_group=args.group,
            version_number=args.version,
            effective_from=args.effective_from,
            effective_to=args.effective_to,
            document_kind=args.kind,
            applies_to=args.applies_to,
        )
        db.commit()
    print(f"registered document {args.document_id} as {args.group} v{args.version}")


if __name__ == "__main__":
    main()
