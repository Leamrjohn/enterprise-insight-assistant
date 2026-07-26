"""Adapter from a persisted tenant schema snapshot to SQL validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotCatalog:
    """Only exposes metadata discovered from one business data source."""

    tables: dict[str, frozenset[str]]
    joins: frozenset[tuple[str, str, str, str]]

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "SnapshotCatalog":
        raw_tables = snapshot.get("tables")
        if not isinstance(raw_tables, dict):
            raise ValueError("Schema snapshot is missing tables metadata")

        tables: dict[str, frozenset[str]] = {}
        for table_name, raw_columns in raw_tables.items():
            if not isinstance(table_name, str) or not isinstance(raw_columns, list):
                raise ValueError("Schema snapshot contains invalid table metadata")
            columns = {
                column["name"]
                for column in raw_columns
                if isinstance(column, dict) and isinstance(column.get("name"), str)
            }
            if not columns:
                raise ValueError(f"Schema snapshot table {table_name!r} has no columns")
            tables[table_name] = frozenset(columns)

        joins: set[tuple[str, str, str, str]] = set()
        raw_joins = snapshot.get("joins", [])
        if not isinstance(raw_joins, list):
            raise ValueError("Schema snapshot contains invalid join metadata")
        for join in raw_joins:
            if not isinstance(join, dict):
                raise ValueError("Schema snapshot contains invalid join metadata")
            left_table = join.get("left_table")
            left_column = join.get("left_column")
            right_table = join.get("right_table")
            right_column = join.get("right_column")
            values = (left_table, left_column, right_table, right_column)
            if not all(isinstance(value, str) for value in values):
                raise ValueError("Schema snapshot contains invalid join metadata")
            if (
                left_table not in tables
                or right_table not in tables
                or left_column not in tables[left_table]
                or right_column not in tables[right_table]
            ):
                raise ValueError(
                    "Schema snapshot join references an unknown table or column"
                )
            joins.add((left_table, left_column, right_table, right_column))

        return cls(tables=tables, joins=frozenset(joins))

    def has_table(self, table_name: str) -> bool:
        return table_name in self.tables

    def columns_for(self, table_name: str) -> frozenset[str]:
        return self.tables.get(table_name, frozenset())

    def allows_join(
        self,
        left_table: str,
        left_column: str,
        right_table: str,
        right_column: str,
    ) -> bool:
        return (left_table, left_column, right_table, right_column) in self.joins or (
            right_table,
            right_column,
            left_table,
            left_column,
        ) in self.joins
