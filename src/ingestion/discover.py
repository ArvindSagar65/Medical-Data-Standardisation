from __future__ import annotations

from pathlib import Path


def discover_json_files(input_dir: Path) -> list[Path]:
    """Return every .json file under input_dir (sorted).

    Production equivalent: list objects under gs://bucket/prefix/.
    """
    return sorted(p for p in input_dir.rglob("*.json") if p.is_file())
