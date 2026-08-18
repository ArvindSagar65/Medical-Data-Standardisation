from __future__ import annotations

from src.config_loader import load_all

ANALYTICS = ("Outlier", "Invalid", "Above Range", "Below Range", "Within Range")


def classify_result(
    canonical_name: str | None,
    result_value: float | None,
    parse_status: str,
    value_type: str,
    range_low: float | None,
    range_high: float | None,
    contradictory: bool = False,
    number_count: int = 1,
) -> str:
    """Assign Test_Name_Analytics (FR-3.1–3.4).

    Order matters: a value like Hb 999 is an Outlier, not merely Above Range.
    Config ranges in reference_ranges.yaml win over OCR range text when present.
    Incoming lab `test_analytics` from the JSON is ignored (often OCR junk).
    """
    cfg_ranges = (load_all()["reference_ranges"].get("tests") or {}).get(canonical_name or "") or {}

    if contradictory and number_count > 2 and value_type == "numeric":
        return "Invalid"

    if value_type == "qualitative":
        if parse_status in {"qualitative", "numeric"}:
            return "Within Range"
        if parse_status == "missing":
            return "Invalid"
        return "Invalid"

    # numeric expected
    if parse_status in {"missing", "non_numeric", "qualitative"} or result_value is None:
        return "Invalid"
    if canonical_name in {None, "UNMAPPED"}:
        return "Invalid"

    outlier_low = cfg_ranges.get("outlier_low")
    outlier_high = cfg_ranges.get("outlier_high")
    if outlier_low is not None and result_value < float(outlier_low):
        return "Outlier"
    if outlier_high is not None and result_value > float(outlier_high):
        return "Outlier"

    low = cfg_ranges.get("low", range_low)
    high = cfg_ranges.get("high", range_high)
    if low is None:
        low = range_low
    if high is None:
        high = range_high
    if low is not None and result_value < float(low):
        return "Below Range"
    if high is not None and result_value > float(high):
        return "Above Range"
    return "Within Range"
