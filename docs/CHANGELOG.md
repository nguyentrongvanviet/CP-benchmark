# v0.3.0

- Added independently generated, validated pilot testsets and extensible packages.
- Added asynchronous Docker C++ judge and offline JSONL model benchmark.
- Added own-account signed Codeforces source import without secret persistence.
- Added sanitized rich statement rendering with bundled KaTeX.
- Added per-test runtime/memory and reproducibility reports.

# v0.2 — Collector reliability and reproducible exports

- Checkpoint every problem and expose its outcome, error and attempt count. Resume retries only incomplete targets.
- Continue after isolated problem failures; stop after exhausted network failures or statement access restrictions.
- Preserve AC metadata when source is restricted; add metadata-only collection and page-cap controls.
- Enforce one collector process per data directory with an OS file lock. Pause interrupts backoff; clean shutdown waits for the request boundary and releases ownership.
- Validate cache hashes/API status; refetch missing/corrupt entries and repair damaged raw blobs with atomic replacement.
- Export all records/references from one SQLite snapshot without per-problem DB reads. Publish content-addressed JSONL and an atomic manifest.
- Keep same-contest problems, declared aliases and exact normalized descriptions together across splits. Compute groups globally before filtering.
- Preserve imported editorial/aliases/provenance when primary HTML verification replaces the imported statement.
- Show per-item results, partial completion, reference modes and verification controls in the UI; refresh catalog after job progress.

## Still limited

- Source retrieval depends on public access; metadata AC is not source code and does not prove local correctness.
- Missing statements, formatting/images, semantic duplicates and model contamination require further data collection and review.
- Main Codeforces catalog coverage excludes private problems and Gym enumeration. Bounded submission scans may miss older accepted code.
- Split proportions are approximate and not rating-stratified; additions can change connected components. Freeze each experiment.
- Test generation, isolated C++ execution, model integration and external submissions remain phase 2. No equivalence to Codeforces hidden tests is claimed.
- Local API/UI are runnable; hosting availability is tracked separately in VALIDATION.md.
