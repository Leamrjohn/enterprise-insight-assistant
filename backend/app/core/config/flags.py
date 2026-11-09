"""Feature switches decided per deployment."""

from __future__ import annotations

from typing import Literal

from app.core.config.base import ConfigDomain


class FeatureFlags(ConfigDomain):
    knowledge_support_check_enabled: bool = True
    # How evidence review marks document boundaries: copied text or sentence numbers.
    review_qualification_mode: Literal["text", "sentence_ref"] = "sentence_ref"
