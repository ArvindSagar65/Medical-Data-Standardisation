# Veritas Claims — Medical Report Standardisation Pipeline

Veritas Claims sits between healthcare providers and insurance payors. Every day it receives 200,000+ medical JSON files from 500+ clinics. Each clinic (and each OCR extractor) names tests differently, mixes units, and sometimes submits the same discharge twice. Analysts cannot compare haemoglobin across sites, auto-adjudication breaks on `"13.7 g/dl"`, and implausible values (Hb `999`) slip into claim approvals.

This repository is a **take-home prototype** of the standardisation pipeline Veritas needs: ingest messy JSON, map it to a canonical schema **without code changes per clinic**, validate ranges/outliers, load an analytics database, and give ops a lightweight console.

The prototype runs entirely on a laptop. Production on Google Cloud is specified in [`docs/architecture.md`](docs/architecture.md) and [`docs/nfr.md`](docs/nfr.md) — that is the Customer Engineer deliverable for scale, SLA, and onboarding.

## 5-minute demo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1. First run — ingest sample-data (official files + malformed + duplicate)
python -m src.pipeline --input sample-data

# 2. Second run — same row counts (idempotent; extras go to dead-letter)
python -m src.pipeline --input sample-data

# 3. Unit tests
pytest -q

# 4. Ops UI
streamlit run src/ui/app.py
# from the repository root (the app adds the project to PYTHONPATH itself)
```

In the UI:

- **Dashboard** — files received / processed / failed / flagged
- **Flagged records** — outliers, out-of-range, Invalid, dead-letter
- **Clinic summary** — FASTTRACK vs ARTEMIS quality rates
- **Record inspector** — raw JSON beside standardised rows (search `claim_no`)
- **Unmapped tests** — add a YAML alias; no code change

What to click on sample data:

| File | What you should see |
|---|---|
| `Sample_JSON_file2.json` | OCR `aemoglobin` → Hemoglobin |
| `Sample_JSON_file5.json` | Second identical discharge suppressed as duplicate |
| `malformed_report.json` | Dead-letter, other files still processed |
| `Sample_JSON_file1_duplicate.json` | Duplicate of file 1 (same bytes / document id) |

## Repository layout

```
config/          # clinic maps, aliases, units, ranges, medicines (zero-code onboarding)
sample-data/     # official JSONs + malformed + duplicate extras
src/ingestion/   # discover, parse, dedup (GCS folder mock)
src/standardisation/
src/validation/
src/loader/      # SQLite = BigQuery mock
src/ui/          # Streamlit = Looker Studio mock
src/pipeline.py
tests/
docs/            # architecture, NFRs, assumptions, draw.io
INPUT_json tables/           # assignment originals (unchanged)
OUTPUT_database table/       # ideal schema CSV from the assignment
```

## Prototype ↔ Google Cloud

| Prototype | Production GCP | Why |
|---|---|---|
| `sample-data/` folder | Cloud Storage (`gs://veritas-raw/{source_system}/{date}/…`) | Object landing zone |
| `python -m src.pipeline` | Cloud Run Jobs (Eventarc on `object.finalize`) or Dataflow | Same Python, horizontal workers |
| `config/*.yaml` | GCS config prefix or Firestore | New clinic = metadata, not a deploy |
| SQLite `data/veritas.db` | BigQuery (canonical long tables + authorised view) | Warehouse scale + SQL |
| Streamlit | Looker Studio + optional Cloud Run inspector | Ops / analyst access |
| `data/dlq/` + `dead_letter` | GCS DLQ prefix + `error_events` table | Poison-message isolation |
| stdout JSON logs | Cloud Logging + Monitoring alert policies | Error rate > 1%, lag > 15 min |

## Design decisions

- **Micro-batch, not streaming.** Files are discrete JSON documents. A 15-minute p95 SLA does not need Dataflow streaming.
- **Schema-on-read, canonical schema-on-write.** Envelope JSONPaths live in config. Output is a **long** lab-results table matching the assignment CSV, plus `claim_tests_wide` for FR-2.2 (five columns per curated test). A 400-column physical table would break zero-code onboarding of new tests.
- **Clinic identity** is `source_system` (`FASTTRACK`, `ARTEMIS`) plus `ConsumerClientId` — the samples are not organised by clinic folder.
- **Config over code.** Aliases, units, ranges, medicines, dedup keys are YAML.
- **Idempotent upserts** on stable SHA-256 ids. Re-running the same prefix does not duplicate facts.
- **One bad file never blocks others.** Malformed JSON is copied to DLQ with a reason.

## Known limitations

- Sample PII is already `[REDACTED]`; demographic parsers are proven in unit tests with synthetic values.
- OCR sometimes swaps test names and units (file 2). We flag Invalid/unmapped rather than guess silently.
- Combined DLC/LFT strings are split when `Name - value` pairs are detected; remaining contradictory blobs are Invalid.
- Not a production GCP deploy, FHIR store, or LOINC/RxNorm terminology service.
- Gemini is **out of the critical path**. It is a future suggestion engine for unmapped aliases with human approval (NFR-4.1).

See [`docs/assumptions.md`](docs/assumptions.md) for business, technical, data, and scope-exclusion reasoning.
