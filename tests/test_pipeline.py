from pathlib import Path

from src.ingestion.parser import ParseError, parse_file
from src.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample-data"


def test_malformed_raises():
    try:
        parse_file(SAMPLE / "malformed_report.json")
        assert False, "expected ParseError"
    except ParseError as exc:
        assert "malformed_json" in exc.reason


def test_pipeline_idempotent_and_dlq(tmp_path):
    db = tmp_path / "veritas.db"
    stats1 = run_pipeline(SAMPLE, db)
    assert stats1["files_received"] >= 7
    assert stats1["files_failed"] >= 1
    assert stats1["files_processed"] >= 5
    stats2 = run_pipeline(SAMPLE, db)
    # Second run: originals are duplicates by document_id / content hash
    assert stats2["files_processed"] == 0
    assert stats2["files_duplicate"] + stats2["files_failed"] == stats2["files_received"]

    import sqlite3

    conn = sqlite3.connect(db)
    lab_n = conn.execute("SELECT COUNT(*) FROM lab_results").fetchone()[0]
    med_n = conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
    claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert lab_n > 20
    assert med_n > 5
    assert claims >= 5
    # File 2 OCR name lands as Hemoglobin
    hb = conn.execute(
        "SELECT COUNT(*) FROM lab_results WHERE test_name_original LIKE '%aemoglobin%' AND test_name_canonical='Hemoglobin'"
    ).fetchone()[0]
    assert hb >= 1
    # File 5 duplicate discharge should not double medications for identical section
    dlq_dup = conn.execute(
        "SELECT COUNT(*) FROM dead_letter WHERE reason LIKE 'duplicate%'"
    ).fetchone()[0]
    assert dlq_dup >= 1
    wide = conn.execute("SELECT COUNT(*) FROM claim_tests_wide").fetchone()[0]
    assert wide == claims
    conn.close()
