"""Small shared helpers for platform adapters."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.core.http import HttpResponse


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_number(*values: Any) -> int | float | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None


def first_number_in(mapping: Mapping[str, Any], keys: Iterable[str]) -> tuple[int | float | None, str | None]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value, key
    return None, None


def ok_code(value: Any, allowed: Iterable[Any] = (0, "0", None, "")) -> bool:
    return value in tuple(allowed)


def response_json(response: HttpResponse) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:300]}
