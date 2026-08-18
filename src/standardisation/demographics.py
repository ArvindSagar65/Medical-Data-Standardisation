from __future__ import annotations

import re
from datetime import datetime

from dateutil import parser as date_parser

AGE_RE = re.compile(
    r"(?:(?P<y>\d+)\s*Y)?\s*(?:(?P<m>\d+)\s*M)?\s*(?:(?P<d>\d+)\s*D)?",
    re.I,
)

GENDER_MAP = {
    "m": "male",
    "male": "male",
    "man": "male",
    "f": "female",
    "female": "female",
    "woman": "female",
    "o": "other",
    "other": "other",
}

PLACEHOLDER_DATES = {"dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd", "date", ""}


def parse_age(age: str | None) -> dict:
    """Parse clinic age strings such as '33Y11M265D' (FR-2.5).

    Redacted sample values are left as text with age_years=None.
    """
    if age is None:
        return {"age_text": None, "age_years": None, "age_months": None, "age_days": None}
    text = str(age).strip()
    if not text or "REDACTED" in text.upper():
        return {"age_text": text or None, "age_years": None, "age_months": None, "age_days": None}
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return {
            "age_text": text,
            "age_years": float(text),
            "age_months": None,
            "age_days": None,
        }
    match = AGE_RE.search(text.replace(" ", ""))
    if not match or not any(match.group(g) for g in ("y", "m", "d")):
        return {"age_text": text, "age_years": None, "age_months": None, "age_days": None}
    years = int(match.group("y") or 0)
    months = int(match.group("m") or 0)
    days = int(match.group("d") or 0)
    return {
        "age_text": text,
        "age_years": round(years + months / 12 + days / 365, 4),
        "age_months": months,
        "age_days": days,
    }


def parse_gender(gender: str | None) -> str | None:
    if gender is None:
        return None
    text = str(gender).strip()
    if not text or "REDACTED" in text.upper():
        return None
    return GENDER_MAP.get(text.lower())


def parse_date(value: str | None, formats: list[str] | None = None) -> str | None:
    """Multiple clinic date formats → ISO 8601 date (FR-2.5)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in PLACEHOLDER_DATES or "REDACTED" in text.upper():
        return None
    # Ignore values that are clearly not dates (e.g. bill_date = LAB10945)
    if re.fullmatch(r"[A-Za-z]+\d+", text):
        return None
    for fmt in formats or []:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return date_parser.parse(text, dayfirst=True, fuzzy=False).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None
