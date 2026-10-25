# Corpus schema 1.0.0

| Field | Meaning |
|---|---|
| id | Stable readable key, e.g. `4A` |
| contest_id, index | Canonical composite problem identity |
| name, rating, tags, type, points | Current Codeforces API fields; absent values remain null |
| url, contest_url, submit_url | Original source links; submit_url alone does not trigger submission |
| contest | Full original Contest object when available |
| statistics | Original ProblemStatistics object |
| raw_problem | Original Problem object including optional fields |
| provenance | API URL, retrieval time UTC, response status, raw SHA-256, MIME, size |
| statement_status | missing / complete (direct HTML) / imported |
| statement | Parsed fields, samples, limits, notes, optional editorial, source kind, provenance, aliases |
| reference_status | missing / metadata_only / complete |
| references | Public Submission metadata plus original link, verdict provenance, source if available, source hash |
| benchmark_ready | Always false in v0.2 |
| judge_status | not_implemented |
| split | Export only; hash of connected contest/alias/exact-description group with seed `cpbench-v1` |

Raw evidence lives at `data/raw/{sha256}`. `fetches` indexes latest URL retrieval; old blobs are retained. SQLite tables are problems, reference_solutions, fetches, jobs, job_items, events. `source_sha256` hashes exact UTF-8 source text; statement `content_sha256` hashes description text only and is useful for exact-duplicate review, not complete statement integrity. Full imported selected-column rows have separate raw evidence hashes. Full export bytes are covered by the manifest.

Unknown source code is null, not an empty accepted program. `reference_kind=accepted_community_submission` never implies official author solution. `verification=codeforces_api_verdict_at_collection` is not local test validation. `local_validation=not_run` is retained explicitly.

## Schema 1.1 / database migration 2

- Export `split_group`: minimum contest ID of the connected component, string encoded.
- Statement `imported_reference`: original supplemental statement/editorial/aliases/provenance retained when primary HTML verification replaces imported text. This is excluded from prompt exports.
- Job item `attempts`: number of processing outcomes recorded, not HTTP requests. States: `pending`, `done`, `partial`, `failed`, `blocked`.
- Job `outcomes`, `succeeded`, `partial`, `failed`: derived counters. `completed_with_errors` means all targets processed with one or more incomplete outcomes. `blocked` targets are not counted as completed.
- Stats `reference_metadata`: distinct problem IDs with accepted reference metadata. `references` requires a source body. Neither field represents independent correctness validation.
- Freeze `file`: content-addressed JSONL filename. `sha256`, `records`, `coverage`, and split counts refer to the same read snapshot.
