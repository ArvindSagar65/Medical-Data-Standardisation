from __future__ import annotations

import re

from src.config_loader import load_all
from src.standardisation.names import normalise_key

SKIP = {"n/a", "na", "nil", "none", "", "if"}

PREFIX_RE = re.compile(r"^(tab|inj|cap|syp|syrup|powder|sachet|amp)\.?\s+", re.I)


def map_medicine(name: str | None) -> dict:
    """Map brand / trade names to a generic INN (FR-2.6).

    'Inj. Pan' → Pantoprazole via config/medicines.yaml. N/A rows are skipped.
    Unknown brands pass through so the claim still has a searchable drug name.
    """
    if name is None:
        return {"original": None, "generic": None, "skipped": True}
    original = str(name).strip()
    compact = original.lower().replace(".", "").replace("/", "").replace(" ", "")
    if compact in {"na", "nil", "none"}:
        return {"original": original, "generic": None, "skipped": True}
    key = normalise_key(PREFIX_RE.sub("", original))
    if key in SKIP or not key:
        return {"original": original, "generic": None, "skipped": True}
    aliases = load_all()["medicines"].get("aliases") or {}
    mapped = {normalise_key(k): v for k, v in aliases.items()}
    if key in mapped:
        return {"original": original, "generic": mapped[key], "skipped": False, "method": "alias"}
    for alias_key, generic in mapped.items():
        if alias_key and alias_key in key:
            return {"original": original, "generic": generic, "skipped": False, "method": "contains"}
    return {"original": original, "generic": original, "skipped": False, "method": "passthrough"}
