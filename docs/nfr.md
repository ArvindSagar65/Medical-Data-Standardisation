# Non-functional requirements — production approach

The prototype does not load 200k files. This note is how the **same modules** meet NFR-1–5 on Google Cloud.

## NFR-1 Scale and performance

**Throughput (NFR-1.1).** 200,000 objects/day ≈ 2.3 files/s average; 400k burst ≈ 4.6/s. Each file is tens to hundreds of KB of JSON. Cloud Run Jobs with Eventarc (one task per object, concurrency 80, CPU 1) handles this with headroom. Dataflow batch is the fallback if CPU-heavy NLP is added later — not required for dictionary + fuzzy matching.

**Latency (NFR-1.2).** Budget inside 15 minutes p95: GCS finalize < 1s, Eventarc < few seconds, Cloud Run cold start < 10s (min instances 1 in business hours), parse+write < 5s typical, BigQuery streaming insert or Storage Write API < 2s. Nightly BigQuery load jobs would miss the SLA; per-object or small micro-batches would not.

**Horizontal scale (NFR-1.3).** Stateless workers. Adding Cloud Run max-instances increases throughput linearly until BigQuery quotas. No shared in-memory clinic state — config is read from GCS/Firestore.

**Cost napkin (order of magnitude, not a quote).** 200k × ~50 KB ≈ 10 GB/day ingress (GCS cheap). 200k Cloud Run-seconds/day at 1 vCPU is a few tens of dollars. BigQuery: streaming inserts cost more than nightly loads; a compromise is 1-minute load jobs of staged GCS JSON to stay under 15 min p95. Storage of raw + canonical is low tens of GB/month at this volume.

**Trade-off:** Cloud Functions (1st gen) per object is simple but weaker CPU/timeouts. GKE is overkill. Dataflow streaming is the “impressive” default and the wrong cost/complexity point until transforms get heavy.

## NFR-2 Clinic onboarding

**Zero-code (NFR-2.1).** `config/clinics.yaml` JSONPaths, `test_aliases.yaml`, `units.yaml`, `medicines.yaml`. Prototype already demonstrates FASTTRACK vs ARTEMIS inheriting `default`.

**One business day (NFR-2.2).** Ops receives a documented sample JSON, adds paths + 20–50 aliases, runs the pipeline on a sandbox prefix, reviews unmapped-test report, promotes YAML. No engineer release.

**Schema versioning (NFR-2.3).** `clinics.yaml` can key `FASTTRACK@v2` selected by object metadata or `metaDetails`. Not wired in the prototype; the merge/`extends` mechanism is the hook.

## NFR-3 Reliability

**Fault isolation (NFR-3.1).** Per-object try/except; DLQ; siblings continue. Pub/Sub dead-letter topic after N delivery attempts.

**Idempotency (NFR-3.2).** Merge on `id = sha256(document_id, record_type, test, page, original)`. Exactly-once warehouse effect from at-least-once Eventarc.

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
- [Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs)
- [BigQuery streaming vs load jobs](https://cloud.google.com/bigquery/docs/loading-data)
- [Cloud DLP](https://cloud.google.com/sensitive-data-protection/docs)
- [Cloud Monitoring alerting](https://cloud.google.com/monitoring/alerts)
