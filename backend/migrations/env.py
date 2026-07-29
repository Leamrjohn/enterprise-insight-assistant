import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from app.db.base import Base
from app.db.session import database_url
from app.models.user import User  # noqa: F401
from app.models.documents import Documents  # noqa: F401
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.analysis_task import AnalysisTask, AnalysisTaskDocument  # noqa: F401
from app.models.conversation import Conversation, ConversationMessage  # noqa: F401
from app.models.todo_items import TodoItem  # noqa: F401
from app.models.labels import Label  # noqa: F401
from app.models.prompt_templates import PromptTemplate  # noqa: F401
from app.models import company  # noqa: F401
from app.models.outbox import AnalysisTaskOutboxEvent  # noqa: F401
from app.models.task_execution_attempt import TaskExecutionAttempt  # noqa: F401
from app.models.workflow_checkpoint import WorkflowCheckpoint  # noqa: F401
from app.models.review_request import ReviewRequest  # noqa: F401
from app.models.analysis_memory import AnalysisMemory  # noqa: F401
from app.models.workflow_event import WorkflowEvent  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
migration_database_user = os.getenv("MIGRATION_DATABASE_USER")
migration_database_url = (
    database_url.set(username=migration_database_user)
    if migration_database_user
    else database_url
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = migration_database_url.render_as_string(hide_password=False)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    with create_engine(migration_database_url).connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
