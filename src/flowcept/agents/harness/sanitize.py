"""Make harness payloads safe and small enough to store as provenance.

Three concerns, in order of importance:

1. **Secrets.** Tool inputs routinely contain API keys (a ``Bash`` command with
   an inline token, an ``env`` dict, a ``.env`` file write). Provenance is
   long-lived and often shared, so redaction happens at capture time, not at
   query time.
2. **Size.** A single ``Write`` can carry a megabyte. Provenance wants the
   shape of the dataflow, not a second copy of the repository.
3. **JSON-safety.** Whatever we emit must survive ``json.dumps``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import CONTENT_FULL, CONTENT_NONE, CONTENT_SUMMARY, Config
from .ids import content_digest

REDACTED = "«redacted»"

#: Key names whose *values* are always dropped.
#:
#: ``auth`` is anchored so it does not swallow ``author``, and the ``token``
#: alternatives all require a credential-ish prefix or suffix -- a bare
#: ``token`` is a secret, but ``input_tokens`` is a number we want to keep.
_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|password|passwd|credential|bearer|"
    r"authorization|auth[_-]|\bauth\b|"
    r"(?:access|refresh|id|api|auth|session|csrf|jwt)[_-]?token|\btokens?\b|"
    r"private[_-]?key|access[_-]?key|session[_-]?key|client[_-]?secret)",
    re.IGNORECASE,
)

#: Checked before :data:`_SECRET_KEY` and wins: these are token *counts*, which
#: are among the most useful things captured provenance holds. Redacting them
#: would be a silent data-quality bug rather than a safety win.
_TOKEN_COUNT_KEY = re.compile(
    r"^(?:(?:input|output|total|prompt|completion|reasoning|cache\w*|max|num|n)[_-]?tokens?"
    r"|tokens?[_-]?(?:count|used|total)"
    r"|tokens)$",
    re.IGNORECASE,
)

#: Literal shapes that look like credentials wherever they appear in text.
_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),  # OpenAI-style
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),  # Anthropic
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),  # GitHub
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

#: Tool-input keys that carry file bodies rather than parameters.
_CONTENT_KEYS = {"content", "new_string", "old_string", "new_str", "old_str", "file_text", "text", "patch", "diff"}

_MAX_DEPTH = 6
_MAX_ITEMS = 100


def redact_text(text: str) -> str:
    """Mask credential-shaped substrings inside free text."""
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def _summarize(text: str) -> dict[str, Any]:
    """Replace a body with its shape: enough to trace, too little to leak."""
    return {
        "_summary": True,
        "chars": len(text),
        "lines": text.count("\n") + 1 if text else 0,
        "sha256_16": content_digest(text),
        "preview": text[:200],
    }


class Sanitizer:
    """Applies redaction, truncation, and JSON-coercion under a `Config`."""

    def __init__(self, config: Config):
        self.config = config

    def value(self, obj: Any, *, key: str | None = None, depth: int = 0) -> Any:
        """Sanitize an arbitrary value for storage."""
        cfg = self.config

        if (
            cfg.redact
            and key
            and not _TOKEN_COUNT_KEY.match(key)
            and _SECRET_KEY.search(key)
            and isinstance(obj, (str, int, float))
        ):
            return REDACTED

        if obj is None or isinstance(obj, (bool, int, float)):
            return obj

        if isinstance(obj, str):
            return self._string(obj, key=key)

        if depth >= _MAX_DEPTH:
            return f"<depth-limit {type(obj).__name__}>"

        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for i, (k, v) in enumerate(obj.items()):
                if i >= _MAX_ITEMS:
                    out["_truncated_keys"] = len(obj) - _MAX_ITEMS
                    break
                out[str(k)] = self.value(v, key=str(k), depth=depth + 1)
            return out

        if isinstance(obj, (list, tuple, set)):
            items = list(obj)
            out_list = [self.value(v, key=key, depth=depth + 1) for v in items[:_MAX_ITEMS]]
            if len(items) > _MAX_ITEMS:
                out_list.append(f"<{len(items) - _MAX_ITEMS} more items>")
            return out_list

        # Anything else: best-effort JSON, else repr.
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return self._string(repr(obj), key=key)

    def _string(self, text: str, *, key: str | None) -> Any:
        cfg = self.config

        is_content = key is not None and key.lower() in _CONTENT_KEYS
        if is_content:
            if cfg.content_mode == CONTENT_NONE:
                return {"_summary": True, "chars": len(text), "omitted": True}
            if cfg.content_mode == CONTENT_SUMMARY:
                summary = _summarize(text)
                if cfg.redact:
                    summary["preview"] = redact_text(summary["preview"])
                return summary
            # CONTENT_FULL falls through to the normal truncation path.
            assert cfg.content_mode == CONTENT_FULL

        if cfg.redact:
            text = redact_text(text)

        if len(text) > cfg.max_str:
            kept = cfg.max_str
            return text[:kept] + f"…<truncated {len(text) - kept} chars>"
        return text

    def mapping(self, obj: Any) -> dict[str, Any]:
        """Sanitize a value that must end up as a dict (``used``/``generated``)."""
        result = self.value(obj)
        if isinstance(result, dict):
            return result
        return {"value": result}
