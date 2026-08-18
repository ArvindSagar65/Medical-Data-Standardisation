from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.config_loader import load_all
from src.loader.schema import SCHEMA_SQL

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "veritas.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


class SqliteLoader:
    """Write canonical tables. Upsert on id so re-runs do not duplicate facts."""
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self._ensure_wide_columns()
        self.conn.commit()

    def _ensure_wide_columns(self) -> None:
        tests = load_all()["canonical_tests"].get("tests") or {}
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(claim_tests_wide)").fetchall()}
        for name in tests:
            for suffix in ("", "_Result", "_Range", "_Unit", "_Analytics"):
                col = _slug(name) + suffix
                if col not in existing:
                    self.conn.execute(f'ALTER TABLE claim_tests_wide ADD COLUMN "{col}" TEXT')
                    existing.add(col)

    def existing_document_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT document_id FROM claims WHERE document_id IS NOT NULL").fetchall()
        return {r[0] for r in rows}

    def existing_file_hashes(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT content_hash FROM file_hashes").fetchall()}

    def existing_section_hashes(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT section_hash FROM section_hashes").fetchall()}

    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO pipeline_runs (started_at) VALUES (?)",
            (_now(),),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, stats: dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at=?, files_received=?, files_processed=?, files_failed=?,
                files_duplicate=?, records_flagged=?, notes=?
            WHERE id=?
            """,
            (
                _now(),
                stats.get("files_received", 0),
                stats.get("files_processed", 0),
                stats.get("files_failed", 0),
                stats.get("files_duplicate", 0),
                stats.get("records_flagged", 0),
                stats.get("notes"),
                run_id,
            ),
        )
        self.conn.commit()

    def upsert(self, table: str, row: dict[str, Any]) -> None:
        cols = [c[1] for c in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
        payload = {k: v for k, v in row.items() if k in cols}
        placeholders = ", ".join("?" for _ in payload)
        assignments = ", ".join(f"{k}=excluded.{k}" for k in payload if k != "id")
        if assignments:
            sql = (
                f"INSERT INTO {table} ({', '.join(payload)}) VALUES ({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET {assignments}"
            )
        else:
            sql = f"INSERT INTO {table} ({', '.join(payload)}) VALUES ({placeholders}) ON CONFLICT(id) DO NOTHING"
        self.conn.execute(sql, list(payload.values()))

    def upsert_many(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            self.upsert(table, row)
            count += 1
        return count

    def write_dead_letter(self, file_path: str, reason: str, snippet: str, document_id: str | None = None, correlation_id: str | None = None) -> None:
        # Keep one row per file+reason so re-runs do not flood the ops log.
        existing = self.conn.execute(
            "SELECT 1 FROM dead_letter WHERE file_path=? AND reason=? LIMIT 1",
            (file_path, reason),
        ).fetchone()
        if existing:
            return
        self.conn.execute(
            """
            INSERT INTO dead_letter (file_path, document_id, correlation_id, reason, snippet, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_path, document_id, correlation_id, reason, snippet[:4000], _now()),
        )

    def remember_file_hash(self, content_hash: str, file_path: str, document_id: str | None) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO file_hashes (content_hash, file_path, document_id, created_at) VALUES (?, ?, ?, ?)",
            (content_hash, file_path, document_id, _now()),
        )

    def remember_section_hash(self, section_hash: str, document_id: str | None, classifier: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO section_hashes (section_hash, document_id, classifier, created_at) VALUES (?, ?, ?, ?)",
            (section_hash, document_id, classifier, _now()),
        )

    def rebuild_wide_table(self) -> None:
        tests = list((load_all()["canonical_tests"].get("tests") or {}).keys())
        self.conn.execute("DELETE FROM claim_tests_wide")
        claims = self.conn.execute("SELECT document_id, claim_no, source_system FROM claims").fetchall()
        for claim in claims:
            row: dict[str, Any] = {
                "document_id": claim["document_id"],
                "claim_no": claim["claim_no"],
                "source_system": claim["source_system"],
            }
            for test in tests:
                lab = self.conn.execute(
                    """
                    SELECT test_name_canonical, result_value, result_text, range_text, unit_canonical, test_analytics
                    FROM lab_results
                    WHERE document_id=? AND test_name_canonical=?
                    ORDER BY page_no ASC
                    LIMIT 1
                    """,
                    (claim["document_id"], test),
                ).fetchone()
                base = _slug(test)
                if lab:
                    display = lab["result_value"] if lab["result_value"] is not None else lab["result_text"]
                    row[base] = test
                    row[base + "_Result"] = None if display is None else str(display)
                    row[base + "_Range"] = lab["range_text"]
                    row[base + "_Unit"] = lab["unit_canonical"]
                    row[base + "_Analytics"] = lab["test_analytics"]
                else:
                    row[base] = None
                    row[base + "_Result"] = None
                    row[base + "_Range"] = None
                    row[base + "_Unit"] = None
                    row[base + "_Analytics"] = None
            cols = list(row.keys())
            placeholders = ", ".join("?" for _ in cols)
            quoted = ", ".join(f'"{c}"' for c in cols)
            self.conn.execute(
                f"INSERT OR REPLACE INTO claim_tests_wide ({quoted}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        self.conn.commit()

    def flagged_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM lab_results WHERE test_analytics IN ('Outlier','Above Range','Below Range','Invalid')"
        ).fetchone()
        return int(row[0])

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
