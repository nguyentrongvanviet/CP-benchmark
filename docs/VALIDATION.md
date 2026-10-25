# Validation of v0.2

Verified 2026-10-14 on macOS, Python 3.14.6.

- Automated: 33 tests passed. Coverage includes per-item failure/retry, single-owner process locking, interruption of backoff, missing/corrupt/FAILED cache responses, network retries and outage stop, metadata-only collection, source restrictions preserving unrelated targets, deterministic connected-group splits, filtered assignment stability, snapshot-consistent immutable exports, API job-item results and preservation of imported evidence. Existing parser, filters, provenance, prompt allowlist and API protections continue to pass. One non-failing Starlette/httpx TestClient deprecation warning remains.
- Static checks: Python compileall and JavaScript syntax validation passed.
- Browser: verified local worker connection, resume after restart, progress counters, per-item result drawer, metadata-only form submission, partial-source result with robots reason, and fresh corpus counts after navigating back. No browser console errors observed.
- Live collection: 200/200 new HTML statements collected; 100/100 new accepted C++ metadata targets completed. A separate source request recorded `completed_with_errors`, one `partial` item and the upstream robots restriction, while preserving AC metadata.
- Current corpus: 11,450 problems; 11,152 rated; 298 unrated. 10,005 statements (205 direct HTML + 9,800 Open R1 imports), leaving 1,445 missing. 6,003 supplemental editorials. 101 problems with accepted C++ metadata; zero retrieved C++ source bodies.
- Integrity audit: 10,024 referenced raw hashes checked, zero failures. 39 exact-description duplicate candidate groups, 1,462 records with declared aliases. 207 statements flagged interactive.
- Export: 1,634 connected split groups; train 9,246 / validation 1,115 / test 1,089. No group crosses splits. This does not establish semantic deduplication or absence of LLM contamination.
- Hosted publication: previous attempts failed during source upload/authentication. Local API, UI and downloadable archives work independently. Publication is being retried using the existing private Site identity; final status is recorded below.

This is a corpus collection platform, not a validated execution benchmark. No generator, sandbox, C++ execution, pass@k, or Codeforces submit integration was tested or claimed.
