"""Ops console over data/veritas.db (FR-5).

Run from the repo root: streamlit run src/ui/app.py
This file adds the project root to sys.path because Streamlit starts in src/ui/.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit puts this file's directory on sys.path, not the repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "veritas.db"


def connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = connect()
    if conn is None:
        return pd.DataFrame()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


st.set_page_config(page_title="Veritas Claims Ops", layout="wide")
st.title("Veritas Claims — operations console")
st.sidebar.markdown(
    "Pipeline health, flagged labs, and raw-vs-standardised inspection. "
    "Run `python -m src.pipeline --input sample-data` before opening this UI."
)

page = st.sidebar.radio(
    "View",
    ["Dashboard", "Flagged records", "Clinic summary", "Record inspector", "Unmapped tests"],
)

if connect() is None:
    st.warning("No database found at data/veritas.db. Run the pipeline against sample-data.")
    st.stop()

if page == "Dashboard":
    st.header("Pipeline dashboard")
    st.caption(
        "**Warehouse** numbers are what analysts query. **Latest job** is the last "
        "`python -m src.pipeline` run. A re-run shows Processed = 0 because files "
        "are already stored (idempotent). That is expected, not a failure."
    )
    totals = load_df(
        """
        SELECT
            (SELECT COUNT(*) FROM claims) AS claims,
            (SELECT COUNT(*) FROM lab_results) AS lab_rows,
            (SELECT COUNT(*) FROM medications) AS medications,
            (SELECT COUNT(*) FROM lab_results
             WHERE test_analytics IN ('Outlier','Above Range','Below Range','Invalid')) AS flagged,
            (SELECT COUNT(*) FROM dead_letter) AS dead_letter_rows
        """
    )
    if not totals.empty:
        t = totals.iloc[0]
        st.subheader("Warehouse (all data loaded so far)")
        w1, w2, w3, w4, w5 = st.columns(5)
        w1.metric("Claims", int(t["claims"] or 0))
        w2.metric("Lab results", int(t["lab_rows"] or 0))
        w3.metric("Medications", int(t["medications"] or 0))
        w4.metric("Flagged labs", int(t["flagged"] or 0))
        w5.metric("Dead-letter rows", int(t["dead_letter_rows"] or 0))

    runs = load_df("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 10")
    if runs.empty:
        st.info("No runs yet.")
    else:
        latest = runs.iloc[0]
        st.subheader("Latest job")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Files received", int(latest["files_received"] or 0))
        c2.metric("Newly processed", int(latest["files_processed"] or 0))
        c3.metric("Failed (unreadable JSON)", int(latest["files_failed"] or 0))
        c4.metric("Duplicates skipped", int(latest["files_duplicate"] or 0))
        c5.metric("Flagged after this job", int(latest["records_flagged"] or 0))
        successful = runs[runs["files_processed"] > 0]
        if not successful.empty:
            last_ok = successful.iloc[0]
            st.info(
                f"Last ingest that added new files: run #{int(last_ok['id'])} "
                f"processed {int(last_ok['files_processed'])} of "
                f"{int(last_ok['files_received'])} files."
            )
        st.subheader("Recent runs")
        st.dataframe(runs, use_container_width=True)
    by_src = load_df(
        "SELECT source_system, COUNT(*) AS claims FROM claims GROUP BY source_system"
    )
    if not by_src.empty:
        st.subheader("Claims by source system")
        st.caption("FASTTRACK vs ARTEMIS from metaDetails — stand-in for clinic/network in this sample pack.")
        st.bar_chart(by_src.set_index("source_system"))
    flags = load_df(
        """
        SELECT test_analytics, COUNT(*) AS n
        FROM lab_results
        GROUP BY test_analytics
        ORDER BY n DESC
        """
    )
    if not flags.empty:
        st.subheader("Analytics classification mix")
        st.caption("Within Range / Above / Below / Outlier / Invalid across all lab_results.")
        st.dataframe(flags, use_container_width=True)

elif page == "Flagged records":
    st.header("Flagged records queue")
    st.caption("Labs that need ops review: physiologically implausible, out of range, or not a usable number.")
    choice = st.multiselect(
        "Flags",
        ["Outlier", "Above Range", "Below Range", "Invalid"],
        default=["Outlier", "Above Range", "Below Range", "Invalid"],
    )
    if choice:
        placeholders = ",".join("?" for _ in choice)
        df = load_df(
            f"""
            SELECT claim_no, document_id, source_system, test_name_original, test_name_canonical,
                   result_value, result_text, unit_canonical, test_analytics, file_gcs_path
            FROM lab_results
            WHERE test_analytics IN ({placeholders})
            ORDER BY test_analytics, test_name_canonical
            """,
            tuple(choice),
        )
        st.dataframe(df, use_container_width=True)
    dlq = load_df("SELECT created_at, reason, file_path, snippet FROM dead_letter ORDER BY id DESC")
    st.subheader("Dead-letter / duplicate log")
    st.dataframe(dlq, use_container_width=True)

elif page == "Clinic summary":
    st.header("Clinic-level data quality")
    st.caption("Grouped by source_system because sample files are not split into clinic folders.")
    df = load_df(
        """
        SELECT
            c.source_system,
            COUNT(DISTINCT c.document_id) AS claims,
            (SELECT COUNT(*) FROM dead_letter d WHERE d.reason LIKE 'duplicate%' AND d.document_id IN
                (SELECT document_id FROM claims c2 WHERE c2.source_system = c.source_system)
            ) AS duplicate_events,
            SUM(CASE WHEN l.test_analytics = 'Invalid' THEN 1 ELSE 0 END) AS invalid_results,
            SUM(CASE WHEN l.test_name_canonical = 'UNMAPPED' THEN 1 ELSE 0 END) AS unmapped_tests,
            COUNT(l.id) AS lab_rows
        FROM claims c
        LEFT JOIN lab_results l ON l.document_id = c.document_id
        GROUP BY c.source_system
        """
    )
    if not df.empty:
        df["unmapped_rate"] = (df["unmapped_tests"] / df["lab_rows"].replace(0, pd.NA)).fillna(0)
        df["invalid_rate"] = (df["invalid_results"] / df["lab_rows"].replace(0, pd.NA)).fillna(0)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No clinic stats yet.")

elif page == "Record inspector":
    st.header("Record inspector")
    st.caption("Search a claim, then compare the original JSON (left) with standardised labs and medicines (right).")
    q = st.text_input("Search claim_no or document_id")
    claims = load_df(
        """
        SELECT document_id, claim_no, source_system, hospital_name, diagnosis, file_gcs_path
        FROM claims
        WHERE (? = '') OR claim_no LIKE ? OR document_id LIKE ?
        ORDER BY claim_no
        """,
        (q, f"%{q}%", f"%{q}%"),
    )
    st.dataframe(claims, use_container_width=True)
    if claims.empty:
        st.stop()
    selected = st.selectbox("Open document", claims["document_id"].tolist())
    raw = load_df("SELECT raw_json FROM claims WHERE document_id = ?", (selected,))
    labs = load_df(
        """
        SELECT test_name_original, test_name_canonical, result_value, result_text,
               unit_original, unit_canonical, range_text, test_analytics, normalization_method
        FROM lab_results WHERE document_id = ?
        """,
        (selected,),
    )
    meds = load_df(
        "SELECT medication_medicine, medicine, dose, frequency FROM medications WHERE document_id = ?",
        (selected,),
    )
    wide = load_df("SELECT * FROM claim_tests_wide WHERE document_id = ?", (selected,))
    left, right = st.columns(2)
    with left:
        st.subheader("Raw JSON (audit)")
        st.code(raw.iloc[0]["raw_json"] if not raw.empty else "", language="json")
    with right:
        st.subheader("Standardised lab results")
        st.dataframe(labs, use_container_width=True)
        st.subheader("Medications (generic mapping)")
        st.dataframe(meds, use_container_width=True)
        st.subheader("FR-2.2 wide test contract (first row)")
        st.dataframe(wide, use_container_width=True)

else:
    st.header("Unmapped tests")
    st.caption("Add aliases to config/test_aliases.yaml — no code change. Production: Gemini can suggest aliases for human approval.")
    df = load_df(
        """
        SELECT test_name_original, COUNT(*) AS n, AVG(normalization_confidence) AS avg_confidence
        FROM lab_results
        WHERE test_name_canonical = 'UNMAPPED'
        GROUP BY test_name_original
        ORDER BY n DESC
        """
    )
    st.dataframe(df, use_container_width=True)
