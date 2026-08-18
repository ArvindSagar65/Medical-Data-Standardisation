from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from src.config_loader import load_all


def normalise_key(name: str | None) -> str:
    text = (name or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_test_name(original: str | None) -> dict:
    """Map Haemoglobin / aemoglobin / OCR fragments to a canonical name (FR-2.1).

    1) exact alias in config/test_aliases.yaml
    2) exact canonical name
    3) RapidFuzz token_set_ratio against canonical names (threshold in YAML)
    Below threshold → UNMAPPED so ops can add an alias without a code change.
    """
    cfg = load_all()
    aliases = {normalise_key(k): v for k, v in (cfg["test_aliases"].get("aliases") or {}).items()}
    canonical = cfg["canonical_tests"].get("tests") or {}
    threshold = int(cfg["canonical_tests"].get("fuzzy_threshold") or 82)
    key = normalise_key(original)
    if not key:
        return {
            "test_name_canonical": None,
            "normalization_method": "empty",
            "normalization_confidence": 0.0,
        }
    if key in aliases:
        return {
            "test_name_canonical": aliases[key],
            "normalization_method": "alias",
            "normalization_confidence": 1.0,
        }
    # Direct canonical hit
    for name in canonical:
        if normalise_key(name) == key:
            return {
                "test_name_canonical": name,
                "normalization_method": "canonical",
                "normalization_confidence": 1.0,
            }
    choices = list(canonical.keys()) + list({v for v in aliases.values()})
    if not choices:
        return {
            "test_name_canonical": None,
            "normalization_method": "unmapped",
            "normalization_confidence": 0.0,
        }
    normalised_choices = [normalise_key(c) for c in choices]
    extracted = process.extractOne(key, normalised_choices, scorer=fuzz.token_set_ratio)
    if not extracted:
        return {
            "test_name_canonical": "UNMAPPED",
            "normalization_method": "unmapped",
            "normalization_confidence": 0.0,
        }
    match, score, _ = extracted
    if score >= threshold:
        lookup = {normalise_key(c): c for c in choices}
        resolved = lookup.get(match)
        # Prefer canonical spelling
        for name in canonical:
            if normalise_key(name) == normalise_key(resolved or ""):
                resolved = name
                break
        return {
            "test_name_canonical": resolved,
            "normalization_method": "fuzzy",
            "normalization_confidence": round(score / 100.0, 4),
        }
    return {
        "test_name_canonical": "UNMAPPED",
        "normalization_method": "unmapped",
        "normalization_confidence": round(score / 100.0, 4),
    }
