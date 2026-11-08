"""Operator command: register or list a company's platform data connections (A11b).

There is no HTTP route for this on purpose: only someone who can run commands on the
platform decides which database a company may reach and which secret it uses.

    python scripts/db/register_data_connection.py list --company-id 7
    python scripts/db/register_data_connection.py add --company-id 7 --name acme-demo \
        --host demo_business_acme --database acme_business --username acme_readonly \
        --credential-env-var ACME_DEMO_DATABASE_PASSWORD --operator alice
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.modules.organizations.connections import new_connection
from app.modules.organizations.models import Company
from app.modules.organizations.service import list_data_connections


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--company-id", type=int, required=True)
    adding = commands.add_parser("add")
    adding.add_argument("--company-id", type=int, required=True)
    adding.add_argument("--name", required=True)
    adding.add_argument("--host", required=True)
    adding.add_argument("--port", type=int, default=5432)
    adding.add_argument("--database", required=True)
    adding.add_argument("--username", required=True)
    adding.add_argument("--schema", default="public")
    adding.add_argument("--credential-env-var", required=True)
    adding.add_argument("--operator", required=True)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if db.get(Company, args.company_id) is None:
            parser.exit(2, f"refused: company {args.company_id} does not exist\n")
        if args.command == "list":
            for item in list_data_connections(db, company_id=args.company_id):
                print(f"{item.id}\t{item.name}\t{item.status}\t{item.host}")
            return
        try:
            connection = new_connection(
                company_id=args.company_id,
                name=args.name,
                host=args.host,
                port=args.port,
                database=args.database,
                username=args.username,
                schema_name=args.schema,
                credential_env_var=args.credential_env_var,
                operator=args.operator,
            )
        except ValueError as exc:
            parser.exit(2, f"refused: {exc}\n")
        db.add(connection)
        db.commit()
        print(f"registered connection {connection.id} for company {args.company_id}")


if __name__ == "__main__":
    main()
