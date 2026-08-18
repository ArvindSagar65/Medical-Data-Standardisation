from __future__ import annotations

import re
from typing import Any

QUALITATIVE = {
    "positive",
    "negative",
    "not detected",
    "detected",
    "nil",
    "absent",
    "present",
    "normal",
    "clear",
    "pale yellow",
    "n/a",
    "na",
}

RANGE_RE = re.compile(
    r"(?P<low>-?\d+(?:[.,]\d+)?)\s*[-–to]+\s*(?P<high>-?\d+(?:[.,]\d+)?)",
    re.I,
)
INEQUALITY_RE = re.compile(r"^\s*(?P<op>[<>]=?)\s*(?P<val>-?\d+(?:[.,]\d+)?)\s*$")
NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+\.\d+|-?\d+")


def _to_float(token: str) -> float:
    return float(token.replace(",", ""))


def parse_numeric(result: Any) -> dict:
    """Pull a float out of messy result strings (FR-2.3).

    Examples: '13.7 g/dl' → 13.7, '4,290 cells/cu.mm' → 4290.
    Words like POSITIVE / NEGATIVE stay non-numeric (parse_status=qualitative).
    """
    if result is None:
        return {"result_value": None, "result_text": None, "parse_status": "missing"}
    text = str(result).strip()
    if not text:
        return {"result_value": None, "result_text": "", "parse_status": "missing"}
    lowered = text.lower().strip()
    if lowered in QUALITATIVE:
        return {"result_value": None, "result_text": text, "parse_status": "qualitative"}

    # Conflicting combined multi-value (many numbers + many names) handled upstream.
    match = NUMBER_RE.search(text)
    if not match:
        return {"result_value": None, "result_text": text, "parse_status": "non_numeric"}
    value = _to_float(match.group(0))
    extra_numbers = NUMBER_RE.findall(text)
    contradictory = len(extra_numbers) > 1 and "," in text and "-" in text and ":" not in text
    return {
        "result_value": value,
        "result_text": text,
        "parse_status": "numeric",
        "contradictory": contradictory,
        "number_count": len(extra_numbers),
    }


def parse_range(range_text: Any) -> dict:
    if range_text is None:
        return {"range_low": None, "range_high": None, "range_text": None}
    text = str(range_text).strip()
    if not text or text.lower() in {"range", "n/a", "na"}:
        return {"range_low": None, "range_high": None, "range_text": text or None}
    ineq = INEQUALITY_RE.match(text.replace("less than", "<").replace("Less than", "<"))
    if ineq:
        val = _to_float(ineq.group("val"))
        op = ineq.group("op")
        if op in {"<", "<="}:
            return {"range_low": None, "range_high": val, "range_text": text}
        return {"range_low": val, "range_high": None, "range_text": text}
    ranged = RANGE_RE.search(text)
    if ranged:
        return {
            "range_low": _to_float(ranged.group("low")),
            "range_high": _to_float(ranged.group("high")),
            "range_text": text,
        }
    return {"range_low": None, "range_high": None, "range_text": text}
