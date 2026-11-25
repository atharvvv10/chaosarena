"""Shared redaction for provider error text.

Keys live only in the gitignored ``.env`` file. Provider exceptions can echo a
request body or header, so every error that may be written to evidence or sent
to the browser passes through this module first.
"""
from __future__ import annotations

import re

_KEY_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"AQ\.Ab[A-Za-z0-9_.-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{16,}", re.IGNORECASE),
)


def redact_text(value: object, limit: int = 300) -> str:
    """Collapse whitespace, truncate, and replace any key-like token."""
    text = " ".join(str(value).split())[:limit]
    for pattern in _KEY_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text
