# Assumptions

Clear assumptions score higher than silent ones. This document is part of the submission, not an appendix afterthought.

## Business assumptions

- Veritas is the **claims processor**, not the EHR. JSON files are already produced by an upstream extraction/OCR layer (FASTTRACK, ARTEMIS). We do not ingest PDFs or HL7 v2 in this design; we standardise what lands in the object store.
- “Clinic” in production is best identified by `source_system` + `ConsumerClientId` in `metaDetails`. The sample pack is not partitioned by clinic folder, despite the brief’s GCS layout assumption. We still **document** the production prefix `gs://…/{source_system}/{date}/{document_id}.json`.
- Deduplication is at **document and section** grain, not “same patient same day.” File 1 and file 3 share a clinical story but different `claim_no` / `documentId` — those are two claims. File 5’s two discharge blocks are the same payload and must collapse.
- Adjudication itself is **out of scope**. We produce clean, flagged facts so rules and fraud models can run later.
- Reference ranges are **generic adult** values for the prototype, not age/sex/lab-specific. A medical director would own production ranges.
- Volume (200k/day) and 15-minute SLA are real production targets; the assignment allows them to be explained rather than load-tested.

## Technical assumptions

- **Local folder + Python + SQLite + Streamlit** is an acceptable GCS / Cloud Run / BigQuery / Looker Studio mock because reviewers must run the repo without our GCP project. The Python modules are written so a Cloud Run **service** can run the same standardise/validate path on a **batch** of objects (the folder loop is that batch).
- SQLite is sufficient for five files and the UI. Production warehouse is **BigQuery** (columnar, authorised views, IAM). PostgreSQL would also satisfy FR-4.1 if Veritas already standardised on Cloud SQL; we would still land a BigQuery replica for analytics.
- RapidFuzz + YAML aliases beat an LLM on the hot path: deterministic, cheap, auditable. Gemini is a **suggestion** service for unmapped strings, with human promotion into YAML.
- Production compute is a Cloud Run **service** (ARM, YAML cached in RAM), not a Job per JSON. Dataflow is only if transforms get heavy. BQ writes are micro-batches (1000 files or 60s; 5000 under backlog) so MERGE volume is hundreds/day, not 200k.
- Idempotent `MERGE` / `INSERT … ON CONFLICT` is enough exactly-once semantics for the warehouse under at-least-once Pub/Sub. Ack after the batch MERGE succeeds.
- No authentication on Streamlit. Production UI sits behind IAP.

## Data assumptions

- Envelope schema is stable (`traceId`, `data.responseDetails[]`, `metaDetails`). Variation is **inside** lab `report_details` and discharge medications — that is what config and fuzzy matching absorb.
- Sample age/gender/names are `[REDACTED]`. Parsers still implement `33Y11M265D`, `M`/`Male`, and mixed date formats; unit tests use synthetic values.
- Incoming `test_analytics` (`normal`, `OTE`, `UV with P-5-P`) is **not** a clinical flag. We recompute `Within Range | Above Range | Below Range | Outlier | Invalid`.
- When a panel appears on many OCR pages (file 4), we keep page-level rows in the long table and take the first page for the wide view. Production may prefer “last non-empty” — a one-line SQL change.
- `lakhs/cumm` → `cells/cu.mm` uses ×100,000 (Indian lab convention). `mil/cu.mm` → million/cu.mm, not millilitres.
- Combined strings (`Neutrophil - 72.4, Lymphocyte - 23.5, …`) are split; leftover multi-value blobs are Invalid (FR-3.4).
- Medicine mapping covers brands present in the samples (Pan, PCM, Ceftum, Dolo, …). Unlisted brands pass through as original text so they remain searchable.
- The ideal schema CSV is **long/narrow** and slightly redundant (overlapping column names). We implemented a cleaned subset aligned to those names rather than 80 nullable duplicates.

## Scope exclusions

| Left out | Why | What production would add |
|---|---|---|
| Live GCS / IAM / VPC / CMEK | 12–24h take-home; reviewers cannot use our project | Terraform + Eventarc + Cloud Run + BQ |
| 200k-file soak test | Not runnable in the assignment window | Cloud Run load + Monitoring dashboard |
| Healthcare API / FHIR | Samples are proprietary JSON, not FHIR | Optional mapping job after canonical tables |
| LOINC / RxNorm | Needs licensed terminology and stewardship | BigQuery lookup tables + weekly refresh |
| Gemini on every record | Cost, non-determinism, audit risk | Batch suggestions for UNMAPPED only |
| Age/sex-specific ranges | Not in sample metadata (redacted) | Range table keyed by test + sex + age band |
| UI auth, audit login, PHI masking toggle | Prototype usability | IAP + DLP + column ACL |
| Draw.io → Google Slides file | Cannot attach a live Slides deck in git | Optional local speaker notes; not in the submitted repo |

Simplifications made to save time are intentional. A well-reasoned prototype with this document is the submission the brief asked for.
