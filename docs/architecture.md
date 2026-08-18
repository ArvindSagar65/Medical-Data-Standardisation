# Solution architecture (prototype + production)

**Veritas Claims Analytics — medical report standardisation**  
Narrative length is scoped to two pages. Non-functional detail lives in [`nfr.md`](nfr.md). Assumptions: [`assumptions.md`](assumptions.md). Diagram: [`architecture.drawio`](architecture.drawio).

## Problem in one paragraph

Clinics send JSON “medical reports” into Veritas’s landing zone. The files share a FASTTRACK/ARTEMIS envelope, but lab rows are OCR-noisy: `aemoglobin`, `4,290 cells/cu.mm`, `POSITIVE`, combined DLC strings, duplicate discharge blocks. Claims analysts need one canonical row per test, medically flagged, auditable back to the source object — at 200k files/day, with new clinics onboarded in config, not code.

## Pattern choice

**Event-driven micro-batch** (not streaming, not a giant nightly warehouse dump). Each object is an independent document. Schema-on-read at the edge; schema-on-write into a canonical model. Streaming Pub/Sub+Dataflow would add cost and operational load without helping the 15-minute p95 SLA.

```
Clinics / existing extractors
        │  PUT JSON
        ▼
Ingestion     Cloud Storage  (prototype: sample-data/)
        │  object.finalize → Eventarc / Pub/Sub
        ▼
Processing    Cloud Run Job  (prototype: src.pipeline)
              parse → dedup → standardise → validate → load
        │
        ├─ success → BigQuery  (prototype: SQLite)
        └─ failure → GCS DLQ + error table
        │
Observability Cloud Logging / Monitoring
UI            Looker Studio + inspector  (prototype: Streamlit)
Config        GCS/Firestore YAML         (prototype: config/)
```

## Layers (FR-1 to FR-5)

**Ingestion.** Production: `gs://veritas-raw/{source_system}/{yyyy}/{mm}/{dd}/{document_id}.json`. Eventarc triggers a Cloud Run task per object; Cloud Scheduler sweeps unprocessed prefixes. Prototype lists `*.json` in a folder. Malformed JSON is isolated (NFR-3.1). Dedup keys (`document_id`, file hash, section hash) are in `config/dedup.yaml` (FR-1.2). File 5’s twin discharge summaries collide on section hash; file 1 vs file 3 keep different `documentId`/`claim_no`.

**Processing.** One Python worker: clinic JSONPaths from `config/clinics.yaml` (FR-1.3, NFR-2.1). Test names: alias dictionary then RapidFuzz (FR-2.1). Numerics and combined fields (FR-2.3). Units + conversion (FR-2.4). Age/gender/ISO dates (FR-2.5). Brand → generic (FR-2.6). Validation priority: Outlier → Invalid → Above/Below Range → Within Range (FR-3). Source `test_analytics` is untrusted OCR.

**Storage.** Long fact tables `lab_results` and `medications` plus `claims` (raw JSON retained, FR-4.3). This matches the assignment’s ideal CSV. FR-2.2’s five columns per test is `claim_tests_wide` (and in production a BigQuery authorised view) so adding Hemoglobin-2 is a YAML row, not an `ALTER TABLE` of 5 columns. Upsert on SHA-256 `id` (NFR-3.2).

**Configuration.** All clinic field maps, aliases, units, ranges, medicines are files. FASTTRACK and ARTEMIS inherit `default`. A new documented schema is a new YAML block (NFR-2.2: one business day).

**Errors.** Per-file try/except; DLQ object + `dead_letter` reason; pipeline continues. Reprocess = copy object back to the raw prefix and replay (idempotent).

**UI.** Streamlit reads SQLite: dashboard, flagged queue, clinic rates, inspector (raw vs canonical), unmapped-test list. Production: Looker Studio on BigQuery for stats; Cloud Run for the JSON inspector if analysts need raw payloads.

## Failure modes

| Failure | Behaviour |
|---|---|
| Malformed JSON | DLQ, reason `malformed_json`, other files proceed |
| OCR junk test name | Fuzzy/alias or `UNMAPPED` + Invalid |
| OCR swapped unit/name (file 2) | Invalid / unmapped; ops adds alias |
| Combined DLC/LFT string | Split when `Name - n` pairs found; else Invalid |
| Placeholder date `DD/MM/YYYY` | Null ISO date |
| Duplicate file or section | Dead-letter `duplicate_*`, no second fact rows |
| Worker crash mid-file | At-least-once replay; upsert makes it exactly-once in the warehouse |

## Trade-offs

| Choice | We took | We rejected | Why |
|---|---|---|---|
| Compute | Cloud Run Jobs | Always-on GKE / Dataflow streaming | 200k small JSON files; scale to zero; 15 min SLA |
| Warehouse | BigQuery | Cloud SQL only | Analyst SQL, cheap scans, views for wide contract |
| Canonical shape | Long + wide view | Only wide 5×N columns | Onboarding new tests must not be a migration |
| Matching | Dictionary + fuzzy | LLM on every row | Deterministic, cheap, auditable; Gemini later for suggestions |
| Prototype DB | SQLite | Live BigQuery | Reviewers can run without a GCP project |

## Assumptions (summary)

JSON already extracted (not PDFs). `source_system` is the clinic/source key. PII redacted in samples; production uses DLP. Prototype does not deploy GCP. See [`assumptions.md`](assumptions.md).
