from app.db.session import engine
from sqlalchemy import inspect


def test_conversation_migration_shape(migrated_test_database: None) -> None:
    inspector = inspect(engine)

    assert {"conversations", "conversation_messages"}.issubset(
        inspector.get_table_names()
    )
    task_columns = {
        column["name"]: column for column in inspector.get_columns("analysis_tasks")
    }
    assert task_columns["conversation_id"]["nullable"] is True
    assert task_columns["input_message_id"]["nullable"] is True
    assert task_columns["context_snapshot"]["type"].__class__.__name__ == "JSONB"

    message_uniques = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("conversation_messages")
    }
    task_uniques = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("analysis_tasks")
    }
    assert ("analysis_task_id",) in message_uniques
    assert ("input_message_id",) in task_uniques

    task_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("analysis_tasks")
    }
    assert task_foreign_keys[("conversation_id",)]["options"]["ondelete"] == "SET NULL"
    assert task_foreign_keys[("input_message_id",)]["options"]["ondelete"] == (
        "SET NULL"
    )
