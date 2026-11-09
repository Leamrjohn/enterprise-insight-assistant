"""Compatibility entry point: settings now live in app/core/config/ (K1).

Existing ``from app.core.settings import get_settings`` imports keep working;
new code may import from ``app.core.config.settings`` directly.
"""

from app.core.config.admission import (
    DEVELOPMENT_CAPACITY_SIGNAL_TOKEN,
    MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS,
)
from app.core.config.base import BACKEND_DIR
from app.core.config.model import EXECUTION_LEASE_SECONDS, MAX_LLM_TIMEOUT_SECONDS
from app.core.config.settings import DOMAINS, Settings, get_settings

__all__ = [
    "BACKEND_DIR",
    "DEVELOPMENT_CAPACITY_SIGNAL_TOKEN",
    "DOMAINS",
    "EXECUTION_LEASE_SECONDS",
    "MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS",
    "MAX_LLM_TIMEOUT_SECONDS",
    "Settings",
    "get_settings",
]
