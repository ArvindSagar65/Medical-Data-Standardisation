from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config_loader import clinic_config
from src.paths import get_path, meta_map


@dataclass
class ParsedSection:
    classifier: str
    data: dict[str, Any]
    status: str | None
    error_message: str | None


@dataclass
class ParsedFile:
    file_path: str
    raw_text: str
    payload: dict[str, Any]
    trace_id: str | None
    correlation_id: str | None
    document_id: str | None
    status_code: Any
    source_system: str
    claim_no: str | None
    nt_code: str | None
    consumer_client_id: str | None
    destination_identifier: str | None
    meta: dict[str, str]
    sections: list[ParsedSection] = field(default_factory=list)


class ParseError(Exception):
    def __init__(self, message: str, file_path: str):
        super().__init__(message)
        self.file_path = file_path
        self.reason = message


def parse_file(path: Path) -> ParsedFile:
    """Parse one extractor envelope into lineage fields + lab/discharge sections.

    Field locations come from config/clinics.yaml (looked up by source_system).
    Malformed JSON raises ParseError so the pipeline can dead-letter this file only.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"malformed_json: {exc}", str(path)) from exc
    if not isinstance(payload, dict):
        raise ParseError("root_not_object", str(path))

    # Peek source_system from meta using the default clinic map.
    default_cfg = clinic_config("default")
    meta = meta_map(get_path(payload, default_cfg["envelope"]["meta_details"], []))
    source_system = meta.get(default_cfg["meta_keys"]["source_system"]) or "default"
    cfg = clinic_config(source_system)
    env = cfg["envelope"]
    keys = cfg["meta_keys"]
    meta = meta_map(get_path(payload, env["meta_details"], []))

    details = get_path(payload, env["response_details"], []) or []
    sections: list[ParsedSection] = []
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            sections.append(
                ParsedSection(
                    classifier=str(item.get("classifier") or "unknown"),
                    data=item.get("data") if isinstance(item.get("data"), dict) else {},
                    status=item.get("status"),
                    error_message=item.get("errorMessage"),
                )
            )

    return ParsedFile(
        file_path=str(path),
        raw_text=raw,
        payload=payload,
        trace_id=get_path(payload, env["trace_id"]),
        correlation_id=get_path(payload, env["correlation_id"]),
        document_id=get_path(payload, env["document_id"]),
        status_code=get_path(payload, env["status_code"]),
        source_system=meta.get(keys["source_system"]) or source_system,
        claim_no=meta.get(keys["claim_no"]),
        nt_code=meta.get(keys["nt_code"]),
        consumer_client_id=meta.get(keys["consumer_client_id"]),
        destination_identifier=meta.get(keys["destination_identifier"]),
        meta=meta,
        sections=sections,
    )
