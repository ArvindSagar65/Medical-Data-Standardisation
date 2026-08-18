"""Split 'Neutrophil - 72.4, Lymphocyte - 23.5' into separate lab rows.

If we cannot split a combined field, validation flags it Invalid (FR-3.4).
"""

from __future__ import annotations

import re

from src.standardisation.names import resolve_test_name

PAIR_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9 +/()%'._-]{1,80}?)\s*[-:=]\s*(-?\d+(?:[.,]\d+)?)",
)


def looks_combined(test_name: str | None, result: str | None) -> bool:
    text = f"{test_name or ''} {result or ''}"
    return len(PAIR_RE.findall(text)) >= 2


def split_combined(test_name: str | None, result: str | None, unit: str | None, range_text: str | None) -> list[dict]:
    blob = result or ""
    if looks_combined(test_name, None) and not str(blob).strip():
        blob = test_name or ""
    pairs = PAIR_RE.findall(blob)
    if len(pairs) < 2:
        pairs = PAIR_RE.findall(f"{test_name or ''} {result or ''}")
    rows = []
    for name, value in pairs:
        resolved = resolve_test_name(name)
        rows.append(
            {
                "test_name_original": name.strip(),
                "test_name_canonical": resolved["test_name_canonical"],
                "normalization_method": resolved["normalization_method"] + "+split",
                "normalization_confidence": resolved["normalization_confidence"],
                "result": value,
                "unit": unit,
                "range": range_text,
                "from_combined": True,
            }
        )
    return rows
