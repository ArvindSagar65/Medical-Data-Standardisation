# Solution architecture (prototype + production)

**Veritas Claims Analytics — medical report standardisation**  
Narrative length is scoped to two pages. Non-functional detail lives in [`nfr.md`](nfr.md). Assumptions: [`assumptions.md`](assumptions.md). Diagram: [`architecture.drawio`](architecture.drawio).

## Problem in one paragraph

Clinics send JSON “medical reports” into Veritas’s landing zone. The files share a FASTTRACK/ARTEMIS envelope, but lab rows are OCR-noisy: `aemoglobin`, `4,290 cells/cu.mm`, `POSITIVE`, combined DLC strings, duplicate discharge blocks. Claims analysts need one canonical row per test, medically flagged, auditable back to the source object — at 200k files/day, with new clinics onboarded in config, not code.

## Pattern choice

**Event-driven micro-batch** (not streaming, not a giant nightly warehouse dump). Files land independently; workers **pull a batch** from Pub/Sub, standardise in process, then one BigQuery `MERGE`. Schema-on-read at the edge; schema-on-write into a canonical model.

Cloud Run **Jobs** are the wrong grain here: a Job per object would create ~200k instance starts/day. A Cloud Run **service** on ARM with concurrency ≈ 80 keeps one warm instance busy with many JSON files. YAML mappings are loaded once into container RAM (same idea as `load_all()` in the prototype).

```
Clinics / existing extractors
        │  PUT JSON
        ▼
Ingestion     Cloud Storage  (prototype: sample-data/)
        │  object.finalize → Eventarc → Pub/Sub
        ▼
Processing    Cloud Run service (ARM)  (prototype: src.pipeline)
              pull batch → parse → dedup → standardise → validate
              YAML aliases/units/ranges cached in RAM
        │
        ├─ flush every 1000 msgs or 60s → BigQuery MERGE
        └─ failure → GCS DLQ + error table
        │
Observability Cloud Logging / Monitoring
UI            Looker Studio + inspector  (prototype: Streamlit)
Config        baked/cached from GCS YAML  (prototype: config/)
```

## Layers (FR-1 to FR-5)

**Ingestion.** Production: `gs://veritas-raw/{source_system}/{yyyy}/{mm}/{dd}/{document_id}.json`. Eventarc publishes the object name to Pub/Sub (not a new Cloud Run instance). Cloud Scheduler sweeps unprocessed prefixes. Prototype lists `*.json` in a folder. Malformed JSON is isolated (NFR-3.1). Dedup keys are in `config/dedup.yaml` (FR-1.2).

**Processing.** Cloud Run **service** (ARM): each instance pulls messages, downloads JSON from GCS, and runs the same Python as this repo. Clinic JSONPaths from cached YAML (FR-1.3, NFR-2.1). Names, numerics, units, demographics, medicines (FR-2). Validation: Outlier → Invalid → Above/Below Range → Within Range (FR-3). Flush when the in-memory batch hits **1000 files or 60 seconds** (whichever first). Under high Pub/Sub backlog, instances raise the flush cap to **5000** so warehouse writes stay batched while Cloud Run autoscaling adds instances. Steady state: 200k files/day ÷ 1000 ≈ **200 MERGEs/day**, not 200k.

**Storage.** Long fact tables plus `claims` (raw JSON, FR-4.3). FR-2.2 five-column layout is a BigQuery authorised view. `MERGE` on SHA-256 `id` (NFR-3.2) for the whole batch.

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
| Worker crash mid-batch | At-least-once Pub/Sub redelivery; batch MERGE on `id` is exactly-once in BQ |

## Trade-offs

| Choice | We took | We rejected | Why |
|---|---|---|---|
| Compute | Cloud Run **service** (ARM, concurrency ~80) | Cloud Run **Job per object**; GKE; Dataflow streaming | Jobs would start ~200k containers/day. One service instance can standardise many JSON files; YAML stays in RAM. |
| Warehouse | BigQuery | Cloud SQL only | Analyst SQL, cheap scans, views for wide contract |
| Canonical shape | Long + wide view | Only wide 5×N columns | Onboarding new tests must not be a migration |
| Matching | Dictionary + fuzzy | LLM on every row | Deterministic, cheap, auditable; Gemini later for suggestions |
| Prototype DB | SQLite | Live BigQuery | Reviewers can run without a GCP project |

## Assumptions (summary)

JSON already extracted (not PDFs). `source_system` is the clinic/source key. PII redacted in samples; production uses DLP. Prototype does not deploy GCP. See [`assumptions.md`](assumptions.md).
