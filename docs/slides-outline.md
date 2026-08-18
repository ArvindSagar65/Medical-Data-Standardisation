# Interview slides outline (Draw.io → Google Slides)

Paste into Google Slides. Pair with `architecture.drawio`.

1. **The business problem** — 200k JSON/day, 500 clinics, Haemoglobin ≠ Hemoglobin, `"13.7 g/dl"` breaks rules, Hb `999` gets paid. Cash flow, fraud, regulation.
2. **Architecture** — GCS → Eventarc → Cloud Run → BigQuery → Looker. Prototype overlay: folder, Python, SQLite, Streamlit. Micro-batch, not streaming.
3. **Zero-code onboarding** — YAML: paths, aliases, units, ranges, medicines. New clinic in one day. Unmapped report → alias, no deploy.
4. **Data quality on *these* files** — file 2 `aemoglobin`; file 4 commas and combined DLC; file 5 duplicate discharge; malformed JSON DLQ.
5. **Trade-offs** — long table + wide view; Cloud Run vs Dataflow; dictionary vs LLM; cost/SLA napkin.
6. **Demo** — run twice (idempotent), UI dashboard, inspector raw vs clean, flagged queue.

Speaker reminder: panel includes a domain lead. Lead with claims outcomes, then architecture, then code.
