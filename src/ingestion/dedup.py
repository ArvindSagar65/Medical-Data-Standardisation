from __future__ import annotations

import hashlib
import json
from typing import Any

from src.config_loader import load_all
from src.ingestion.parser import ParsedFile, ParsedSection


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_content_hash(parsed: ParsedFile) -> str:
    return _sha(parsed.raw_text)


def section_hash(parsed: ParsedFile, section: ParsedSection) -> str:
    cfg = load_all()["dedup"]
    fields = cfg.get("section_hash_fields") or []
    payload: dict[str, Any] = {
        "classifier": section.classifier,
        "diagnosis": section.data.get("diagnosis"),
        "admission_date": section.data.get("admissionDate"),
        "discharge_date": section.data.get("dischargeDate"),
        "claim_no": parsed.claim_no,
        "document_id": parsed.document_id,
    }
    # Restrict to configured keys when present.
    trimmed = {k: payload.get(k) for k in fields} if fields else payload
    trimmed["body"] = json.dumps(section.data, sort_keys=True, default=str)
    return _sha(json.dumps(trimmed, sort_keys=True, default=str))


class DedupIndex:
    """Suppress duplicate files and duplicate sections (FR-1.2).

    Strategies are listed in config/dedup.yaml:
    - file_content_hash: exact byte replay (Sample_JSON_file1_duplicate.json)
    - document_id: same extractor document sent again
    - section_hash: identical discharge/lab block inside one file (file 5)
    """

    def __init__(self, existing_document_ids: set[str], existing_section_hashes: set[str], existing_file_hashes: set[str]):
        self.document_ids = set(existing_document_ids)
        self.section_hashes = set(existing_section_hashes)
        self.file_hashes = set(existing_file_hashes)

    def is_file_duplicate(self, parsed: ParsedFile) -> tuple[bool, str | None]:
        strategies = load_all()["dedup"].get("strategies") or []
        digest = file_content_hash(parsed)
        if "file_content_hash" in strategies and digest in self.file_hashes:
            return True, "duplicate_file_content"
        if "document_id" in strategies and parsed.document_id and parsed.document_id in self.document_ids:
            return True, "duplicate_document_id"
        return False, None

    def remember_file(self, parsed: ParsedFile) -> None:
        if parsed.document_id:
            self.document_ids.add(parsed.document_id)
        self.file_hashes.add(file_content_hash(parsed))

    def is_section_duplicate(self, parsed: ParsedFile, section: ParsedSection) -> tuple[bool, str | None]:
        strategies = load_all()["dedup"].get("strategies") or []
        if "section_hash" not in strategies:
            return False, None
        digest = section_hash(parsed, section)
        if digest in self.section_hashes:
            return True, "duplicate_section"
        return False, None

    def remember_section(self, parsed: ParsedFile, section: ParsedSection) -> None:
        self.section_hashes.add(section_hash(parsed, section))
