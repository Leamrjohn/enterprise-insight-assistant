"""Regenerate Markdown knowledge-base files without resetting business data."""

from generate_business_data import db_connection, generate_business_knowledge_base


def main() -> None:
    with db_connection() as conn, conn.cursor() as cur:
        generate_business_knowledge_base(cur)
    print("Business knowledge-base corpus generated from the current database.")


if __name__ == "__main__":
    main()
