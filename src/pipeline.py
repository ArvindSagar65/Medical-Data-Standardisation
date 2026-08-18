"""Run one batch: discover JSON → parse → dedup → standardise → validate → SQLite.

A local folder stands in for a GCS bucket (FR-1.1). One corrupt file is copied to
data/dlq/ and recorded in dead_letter; remaining files still process (NFR-3.1).
Re-running the same folder upserts by stable ids and skips known hashes (NFR-3.2).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.config_loader import ROOT
from src.ingestion.dedup import DedupIndex, file_content_hash, section_hash
from src.ingestion.discover import discover_json_files
from src.ingestion.parser import ParseError, parse_file
from src.loader.sqlite_loader import SqliteLoader
from src.logging_utils import get_logger
from src.standardisation.transform import claim_row, lab_rows, medication_rows

log = get_logger("veritas.pipeline")
DLQ_DIR = ROOT / "data" / "dlq"


def _copy_dlq(path: Path) -> Path:
    DLQ_DIR.mkdir(parents=True, exist_ok=True)
    dest = DLQ_DIR / path.name
    shutil.copy2(path, dest)
    return dest


def run_pipeline(input_dir: Path, db_path: Path | None = None) -> dict:
    loader = SqliteLoader(db_path)
    run_id = loader.start_run()
    dedup = DedupIndex(
        loader.existing_document_ids(),
        loader.existing_section_hashes(),
        loader.existing_file_hashes(),
    )
    stats = {
        "files_received": 0,
        "files_processed": 0,
        "files_failed": 0,
        "files_duplicate": 0,
        "records_flagged": 0,
        "notes": None,
    }
    files = discover_json_files(input_dir)
    stats["files_received"] = len(files)

    for path in files:
        extra = {"file_path": str(path), "step": "ingest"}
        try:
            parsed = parse_file(path)
        except ParseError as exc:
            stats["files_failed"] += 1
            _copy_dlq(path)
            loader.write_dead_letter(str(path), exc.reason, path.read_text(encoding="utf-8", errors="replace")[:500])
            log.error("file_failed", extra={**extra, "reason": exc.reason})
            continue
        extra.update(
            {
                "correlation_id": parsed.correlation_id,
                "trace_id": parsed.trace_id,
                "document_id": parsed.document_id,
            }
        )
        is_dup, reason = dedup.is_file_duplicate(parsed)
        if is_dup:
            stats["files_duplicate"] += 1
            loader.write_dead_letter(str(path), reason or "duplicate", parsed.raw_text[:500], parsed.document_id, parsed.correlation_id)
            log.info("file_duplicate", extra={**extra, "reason": reason})
            continue

        kept_sections = []
        for section in parsed.sections:
            sec_dup, sec_reason = dedup.is_section_duplicate(parsed, section)
            if sec_dup:
                loader.write_dead_letter(
                    str(path),
                    sec_reason or "duplicate_section",
                    str(section.data)[:500],
                    parsed.document_id,
                    parsed.correlation_id,
                )
                log.info("section_duplicate", extra={**extra, "reason": sec_reason, "step": "dedup"})
                continue
            kept_sections.append(section)
            dedup.remember_section(parsed, section)
            loader.remember_section_hash(section_hash(parsed, section), parsed.document_id, section.classifier)

        if not kept_sections:
            stats["files_duplicate"] += 1
            continue

        claim = claim_row(parsed, kept_sections)
        loader.upsert("claims", claim)
        for section in kept_sections:
            if section.classifier == "lab_report":
                loader.upsert_many("lab_results", lab_rows(parsed, section))
            elif section.classifier == "discharge_summary":
                loader.upsert_many("medications", medication_rows(parsed, section))
        dedup.remember_file(parsed)
        loader.remember_file_hash(file_content_hash(parsed), parsed.file_path, parsed.document_id)
        stats["files_processed"] += 1
        log.info("file_processed", extra={**extra, "step": "load"})

    loader.commit()
    loader.rebuild_wide_table()
    stats["records_flagged"] = loader.flagged_count()
    loader.finish_run(run_id, stats)
    loader.close()
    log.info("run_complete", extra={"step": "complete", "reason": str(stats)})
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Veritas Claims standardisation pipeline")
    parser.add_argument("--input", default="sample-data", help="Folder of JSON files (GCS mock)")
    parser.add_argument("--db", default=None, help="SQLite path")
    args = parser.parse_args()
    input_dir = Path(args.input)
    if not input_dir.is_absolute():
        input_dir = ROOT / input_dir
    stats = run_pipeline(input_dir, Path(args.db) if args.db else None)
    print(stats)


if __name__ == "__main__":
    main()
