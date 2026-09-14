"""Schema discovery only reads metadata and records actual foreign keys."""

from types import SimpleNamespace

from app.modules.analysis.schema_discovery import discover_postgres_schema


class FakeCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[str]]] = []
        self._fetch_index = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[str]) -> None:
        self.executions.append((query, parameters))

    def fetchall(self) -> list[tuple[str, ...]]:
        results: list[list[tuple[str, ...]]] = [
            [
                ("inventory_balances", "product_id", "integer", "NO"),
                ("inventory_balances", "on_hand", "integer", "NO"),
                ("products", "id", "integer", "NO"),
                ("products", "sku", "character varying", "NO"),
            ],
            [("inventory_balances", "product_id", "products", "id")],
        ]
        result = results[self._fetch_index]
        self._fetch_index += 1
        return result


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_discovers_columns_and_foreign_keys(monkeypatch) -> None:
    connection = FakeConnection()
    monkeypatch.setenv("ACME_DB_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(
        "app.modules.analysis.schema_discovery.psycopg.connect", lambda **_: connection
    )
    source = SimpleNamespace(
        dialect="postgresql",
        credential_env_var="ACME_DB_PASSWORD",
        connection_config={
            "host": "db",
            "port": 5432,
            "database": "acme",
            "user": "readonly",
            "schema": "public",
        },
    )

    catalog, fingerprint = discover_postgres_schema(source)

    assert catalog["tables"]["inventory_balances"][0]["name"] == "product_id"
    assert catalog["joins"] == [
        {
            "left_table": "inventory_balances",
            "left_column": "product_id",
            "right_table": "products",
            "right_column": "id",
        }
    ]
    assert len(fingerprint) == 64
    assert len(connection.cursor_instance.executions) == 2
    assert all(
        params == ("public",) for _, params in connection.cursor_instance.executions
    )
