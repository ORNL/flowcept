"""Sanitization helpers for JSON-like provenance data."""

from __future__ import annotations

import re
from typing import Any, Dict

SENSITIVE_KEY_PATTERNS = ("api_key", "access_key", "token", "secret", "password", "passwd", "credentials")
SENSITIVE_VALUE_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]+")


def _redact_key_value(key: str, value: Any) -> Any:
    key_l = key.lower()
    if any(pat in key_l for pat in SENSITIVE_KEY_PATTERNS):
        return "REDACTED"
    if isinstance(value, str) and SENSITIVE_VALUE_PATTERN.search(value):
        return "REDACTED"
    return value


def sanitize_json_like(value: Any) -> Any:
    """Recursively sanitize dict/list structures."""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            out[str(k)] = sanitize_json_like(_redact_key_value(str(k), v))
        return out
    if isinstance(value, list):
        return [sanitize_json_like(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_json_like(v) for v in value]
    if isinstance(value, str) and SENSITIVE_VALUE_PATTERN.search(value):
        return "REDACTED"
    return value
