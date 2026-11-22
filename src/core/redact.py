"""Masking and redaction helpers.

No secret value should reach logs, state files or error messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, repr=False)
class SensitiveStr:
    """A string whose repr/str never exposes the underlying value."""

    value: str

    def reveal(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "SensitiveStr(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


def mask_account(value: str | None) -> str:
    """Mask an account label without leaking the raw identifier."""

    text = (value or "").strip()
    if not text:
        return "***"
    if "***" in text:
        return text
    if "@" in text:
        text = text.split("@", 1)[0]
    if len(text) <= 2:
        return "***"
    keep = 1 if len(text) <= 4 else 2
    return f"{text[:keep]}***{text[-keep:]}"


_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer <REDACTED>"),
    (
        re.compile(
            r"(?i)\b(access_token|refresh_token|id_token|token|password|passwd|pwd|cookie|authorization|secret|turnstile)\b"
            r"\s*[:=]\s*[\"']?[^\"'\s,;]+"
        ),
        r"\1=<REDACTED>",
    ),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "<REDACTED>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "<REDACTED>"),
    (re.compile(r"\bnap_[A-Za-z0-9]{20,}\b"), "<REDACTED>"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "<REDACTED>"),
    (re.compile(r"\b(?:pt|dt)-[A-Za-z0-9._-]{16,}\b"), "<REDACTED>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "<REDACTED>"),
    (re.compile(r"([?&](?:token|turnstile|key|secret|password|cookie)=)[^&\s]+"), r"\1<REDACTED>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
)

_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "passwd",
    "pwd",
    "cookie",
    "authorization",
    "secret",
    "turnstile",
    "turnstile_token",
    "kk_turnstile_token",
}


def redact_text(value: str | None, *, max_len: int = 500) -> str:
    """Redact known secret patterns and collapse whitespace."""

    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def redact_mapping(value: Any) -> Any:
    """Recursively redact mappings and strings."""

    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                result[key] = "<REDACTED>"
            else:
                result[key] = redact_mapping(item)
        return result
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_mapping(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


_TURNSTILE_LOG_KEYS = (
    "detected",
    "mode",
    "attempts",
    "clicks",
    "result",
    "manual_required",
    "duration_ms",
    "token_present",
)


def redact_turnstile(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Keep only non-sensitive Turnstile observation fields."""

    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in _TURNSTILE_LOG_KEYS:
        if key in value:
            result[key] = value[key]
    if "token" in value or "turnstile_token" in value:
        result["token_present"] = bool(value.get("token") or value.get("turnstile_token"))
    return result or None
