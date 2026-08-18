from __future__ import annotations

from src.config_loader import load_all
from src.standardisation.names import normalise_key


def _unit_key(unit: str | None) -> str:
    return (unit or "").strip().lower()


def canonical_unit(unit: str | None) -> str | None:
    if unit is None or str(unit).strip() == "":
        return None
    aliases = load_all()["units"].get("aliases") or {}
    key = _unit_key(unit)
    if key in aliases:
        mapped = aliases[key]
        return mapped if mapped != "" else None
    return str(unit).strip()


def convert_value(value: float | None, from_unit: str | None, to_unit: str | None) -> tuple[float | None, str | None]:
    """Map unit aliases and apply a conversion factor (FR-2.4).

    Example: 1.90 lakhs/cumm → 190000 cells/cu.mm (config/units.yaml).
    """
    if value is None:
        return None, canonical_unit(from_unit) or to_unit
    src = canonical_unit(from_unit)
    dst = to_unit or src
    if not src or not dst or src == dst:
        return value, dst or src
    for rule in load_all()["units"].get("conversions") or []:
        if rule.get("from") == src and rule.get("to") == dst:
            return value * float(rule["factor"]), dst
        # chained: lakhs -> cells when destination is cells
        if rule.get("from") == src and rule.get("to") == dst:
            return value * float(rule["factor"]), dst
    # try convert src to dst via any matching conversion whose to equals dst
    for rule in load_all()["units"].get("conversions") or []:
        if normalise_key(rule.get("from")) == normalise_key(src) and rule.get("to") == dst:
            return value * float(rule["factor"]), dst
    return value, src
