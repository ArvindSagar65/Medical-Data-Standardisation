"""Load YAML from /config so a new clinic does not require a code change (NFR-2.1).

`clinics.yaml` entries may set `extends: default` to inherit JSON field paths.
`load_all()` is cached for one process; restart the pipeline after editing YAML.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def _read_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key == "extends":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def load_all() -> dict[str, Any]:
    clinics = _read_yaml("clinics.yaml")
    default = clinics.get("default") or {}
    resolved = {}
    for name, spec in clinics.items():
        if name == "default":
            resolved[name] = default
            continue
        spec = spec or {}
        parent_name = spec.get("extends", "default")
        parent = clinics.get(parent_name) or default
        if parent_name != "default":
            parent = _deep_merge(default, parent)
        resolved[name] = _deep_merge(parent, spec)
    return {
        "clinics": resolved,
        "canonical_tests": _read_yaml("canonical_tests.yaml"),
        "test_aliases": _read_yaml("test_aliases.yaml"),
        "units": _read_yaml("units.yaml"),
        "reference_ranges": _read_yaml("reference_ranges.yaml"),
        "medicines": _read_yaml("medicines.yaml"),
        "dedup": _read_yaml("dedup.yaml"),
    }


def clinic_config(source_system: str | None) -> dict[str, Any]:
    clinics = load_all()["clinics"]
    key = (source_system or "default").strip()
    return clinics.get(key) or clinics["default"]
