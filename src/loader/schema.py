SCHEMA_SQL = """
-- Canonical warehouse (prototype SQLite; production would be BigQuery).
-- lab_results is long-format. claim_tests_wide is the FR-2.2 pivot.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    files_received INTEGER DEFAULT 0,
    files_processed INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    files_duplicate INTEGER DEFAULT 0,
    records_flagged INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    record_type TEXT,
    file_gcs_path TEXT,
    trace_id TEXT,
    correlation_id TEXT,
    source_system TEXT,
    claim_no TEXT,
    nt_code TEXT,
    consumer_client_id TEXT,
    destination_identifier TEXT,
    patient_name TEXT,
    age TEXT,
    age_text TEXT,
    age_years REAL,
    gender TEXT,
    uhid TEXT,
    hospital_name TEXT,
    hospital_address TEXT,
    doctor_name TEXT,
    lab_or_hospital_name TEXT,
    bill_date TEXT,
    reports_date TEXT,
    report_date TEXT,
    admission_date TEXT,
    discharge_date TEXT,
    diagnosis TEXT,
    brief_history TEXT,
    general_examinations TEXT,
    recommendations TEXT,
    ward TEXT,
    post_discharge_advice TEXT,
    medicine_injections_investigation TEXT,
    course_during_hospitalisation TEXT,
    basic_info_age TEXT,
    basic_info_bill_date TEXT,
    metadetails TEXT,
    raw_json TEXT,
    processed_at TEXT,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    record_type TEXT,
    file_gcs_path TEXT,
    trace_id TEXT,
    correlation_id TEXT,
    source_system TEXT,
    claim_no TEXT,
    nt_code TEXT,
    consumer_client_id TEXT,
    destination_identifier TEXT,
    test_name_canonical TEXT,
    test_name_original TEXT,
    result_value REAL,
    result_text TEXT,
    result_text_original TEXT,
    unit_canonical TEXT,
    unit_original TEXT,
    range_low REAL,
    range_high REAL,
    range_text TEXT,
    range_text_original TEXT,
    test_analytics TEXT,
    normalization_method TEXT,
    normalization_confidence REAL,
    page_no INTEGER,
    processed_at TEXT,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS medications (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    record_type TEXT,
    file_gcs_path TEXT,
    trace_id TEXT,
    correlation_id TEXT,
    source_system TEXT,
    claim_no TEXT,
    medicine TEXT,
    medication_name TEXT,
    medication_medicine TEXT,
    dose TEXT,
    frequency TEXT,
    medicine_type TEXT,
    medication_dose TEXT,
    medication_frequency TEXT,
    processed_at TEXT,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT,
    document_id TEXT,
    correlation_id TEXT,
    reason TEXT,
    snippet TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS file_hashes (
    content_hash TEXT PRIMARY KEY,
    file_path TEXT,
    document_id TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS section_hashes (
    section_hash TEXT PRIMARY KEY,
    document_id TEXT,
    classifier TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS claim_tests_wide (
    document_id TEXT PRIMARY KEY,
    claim_no TEXT,
    source_system TEXT
);
"""
