from __future__ import annotations

from typing import Any


def get_path(obj: Any, path: str | None, default: Any = None) -> Any:
    """Read nested JSON using a dotted path from clinics.yaml, e.g. data.correlationId."""
    if not path:
        return default
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def meta_map(meta_details: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(meta_details, list):
        return out
    for item in meta_details:
        if isinstance(item, dict) and item.get("key"):
            out[str(item["key"])] = "" if item.get("value") is None else str(item["value"])
    return out
