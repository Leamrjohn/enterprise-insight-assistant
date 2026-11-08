"""Platform-registered business database connections (A11b).

A tenant data source reaches a database only through a connection the platform
registered for that same company. Every check runs before a socket is opened.
"""

from __future__ import annotations

import os
from typing import TypedDict

from app.modules.organizations.data_source_policy import ensure_data_source_allowed
from app.modules.organizations.models import BusinessDataSource, PlatformDataConnection

ENV_SCHEME = "env:"


class ConnectionNotAllowed(ValueError):
    """The source has no usable connection of its own company."""


class ConnectionDetails(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    schema: str
    password: str


def new_connection(
    *,
    company_id: int,
    name: str,
    host: str,
    port: int,
    database: str,
    username: str,
    schema_name: str,
    credential_env_var: str,
    operator: str,
) -> PlatformDataConnection:
    """Build an operator-registered connection; the caller adds and commits it."""
    ensure_data_source_allowed(credential_env_var=credential_env_var, host=host)
    return PlatformDataConnection(
        company_id=company_id,
        name=name,
        host=host,
        port=port,
        database=database,
        username=username,
        schema_name=schema_name,
        credential_ref=ENV_SCHEME + credential_env_var,
        status="active",
        created_by_operator=operator,
    )


def resolve_connection(source: BusinessDataSource) -> ConnectionDetails:
    connection = source.connection
    if connection is None:
        raise ConnectionNotAllowed("data source is not bound to a platform connection")
    if connection.company_id != source.company_id:
        raise ConnectionNotAllowed("data source points at another company's connection")
    if connection.status != "active":
        raise ConnectionNotAllowed("platform connection is not active")
    if not connection.credential_ref.startswith(ENV_SCHEME):
        raise ConnectionNotAllowed("platform connection credential is not supported")
    credential_env_var = connection.credential_ref.removeprefix(ENV_SCHEME)
    # A11a still applies: rows registered before a rule tightened stay covered.
    ensure_data_source_allowed(
        credential_env_var=credential_env_var, host=connection.host
    )
    password = os.environ.get(credential_env_var)
    if not password:
        raise ValueError("配置的数据源凭据不可用")
    return {
        "host": connection.host,
        "port": connection.port,
        "dbname": connection.database,
        "user": connection.username,
        "schema": connection.schema_name,
        "password": password,
    }
