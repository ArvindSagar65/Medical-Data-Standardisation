# Non-functional requirements — production approach

The prototype does not load 200k files. This note is how the **same modules** meet NFR-1–5 on Google Cloud.

## NFR-1 Scale and performance

**Throughput (NFR-1.1).** 200,000 objects/day ≈ 2.3 files/s average; 400k burst ≈ 4.6/s. Small JSON (tens–hundreds of KB). A Cloud Run **service** on ARM handles this: **one instance processes many files** (target ≥ 80 JSON per instance via Pub/Sub pull + HTTP concurrency). A **Job per upload** would create an instance per object — startup and billing overhead at 200k/day, which we reject. Dataflow remains a fallback only if transforms become CPU-heavy (PDF/NLP), not for dictionary + fuzzy matching.

**Latency (NFR-1.2).** Batch window is **60 seconds or 1000 messages** (5000 under backlog). That flush is still far inside a 15-minute p95: GCS finalize + Pub/Sub + process + one BQ `MERGE`. Min instances ≥ 1 in claim hours avoids cold-start on the first file of a quiet period. Nightly loads would miss the SLA; per-file MERGE would not miss SLA but would hammer BigQuery.

**Horizontal scale (NFR-1.3).** Autoscaling adds **service instances** when CPU or Pub/Sub unacked messages rise. Throughput scales roughly linearly. Batch size is a **worker setting**, not something Cloud Run changes by itself: at steady state flush at 1000; if lag/backlog grows, raise the cap to 5000 so MERGE rate stays bounded while more ARM instances drain the subscription. YAML is **in RAM** after container start (refresh from GCS on a generation/etag check, not on every file).

**Cost napkin (order of magnitude, not a quote).** 200k × ~50 KB ≈ 10 GB/day GCS. Cloud Run: a handful of ARM instances, not 200k Job executions. BigQuery: **~200 MERGEs/day** at 1000-file batches (200k÷1000), vs 200k single-row merges. Burst path: 5000-file batches → even fewer MERGE jobs while instances scale out. Storage of raw + canonical is low tens of GB/month.

**Trade-off:** Cloud Functions per object has the same “one invoke per file” tax. GKE is overkill. Dataflow streaming is the impressive default and the wrong cost point until transforms get heavy. Cloud Run Jobs stay useful for **scheduled sweeps** (DLQ replay, unprocessed prefix), not the hot path.

## NFR-2 Clinic onboarding

**Zero-code (NFR-2.1).** `config/clinics.yaml` JSONPaths, `test_aliases.yaml`, `units.yaml`, `medicines.yaml`. Prototype already demonstrates FASTTRACK vs ARTEMIS inheriting `default`.

**One business day (NFR-2.2).** Ops receives a documented sample JSON, adds paths + 20–50 aliases, runs the pipeline on a sandbox prefix, reviews unmapped-test report, promotes YAML. No engineer release.

**Schema versioning (NFR-2.3).** `clinics.yaml` can key `FASTTRACK@v2` selected by object metadata or `metaDetails`. Not wired in the prototype; the merge/`extends` mechanism is the hook.

## NFR-3 Reliability

**Fault isolation (NFR-3.1).** Per-object try/except; DLQ; siblings continue. Pub/Sub dead-letter topic after N delivery attempts.

**Idempotency (NFR-3.2).** Batch `MERGE` on `id = sha256(document_id, record_type, test, page, original)`. Exactly-once warehouse effect despite at-least-once Pub/Sub. Ack the batch only after MERGE succeeds (or nack and retry).

**Availability (NFR-3.3).** Regional Cloud Run + multi-region GCS + BigQuery SLA. 99.5% allows ~3.6h/month; keep maintenance to config reloads (no downtime) and document a <2h window for forced deploys. Min instances during peak claim hours.

## NFR-4 Data quality and governance

**98% alias coverage in 30 days (NFR-4.1).** Unmapped report in the UI. Weekly ops review. Optional Gemini batch job proposes aliases; humans write YAML. Never auto-apply LLM labels to paid claims.

**Lineage (NFR-4.2).** `file_gcs_path`, `trace_id`, `correlation_id`, `document_id`, `source_system`, `ingested_at`, `processed_at` on every row (present in samples and in SQLite).

**PII (NFR-4.3).** Samples are redacted. Production: Cloud DLP inspect/de-identify on landing, CMEK, column-level security in BigQuery, no patient name in Looker dashboards by default. Tokenise UHID/claim_no if downstream is a vendor.

## NFR-5 Observability

**Metrics/alerts (NFR-5.1).** Cloud Run request count, error rate, execution time; custom metrics: files_ok, files_fail, unmapped_ratio, lag = now − object timeCreated. Alert: error rate > 1% for 10 min; lag p95 > 15 min.

**Logs (NFR-5.2).** JSON logs with `correlation_id` / `trace_id` / `document_id` / `step` (prototype already emits this shape). Cloud Trace optional via the incoming `traceId`.

## References

- [Cloud Storage object notifications / Eventarc](https://cloud.google.com/eventarc/docs/event-types)
- [Cloud Run services](https://cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Pub/Sub flow control and pull](https://cloud.google.com/pubsub/docs/pull)
- [BigQuery streaming vs load jobs](https://cloud.google.com/bigquery/docs/loading-data)
- [Cloud DLP](https://cloud.google.com/sensitive-data-protection/docs)
- [Cloud Monitoring alerting](https://cloud.google.com/monitoring/alerts)
