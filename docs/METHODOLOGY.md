# Methodology v0.2

## Objective and scope

Construct a traceable corpus for future evaluation of LLM competitive programming ability. The implementation currently measures collection coverage, not model ability. No generated test set, sandbox, reference validation, model adapter, or judge parity claim exists in v0.2.

## Collection design

1. Download `problemset.problems` and `contest.list` using the public Codeforces API. Retain all returned optional fields and unrated tasks. IDs are contest ID + problem index. Public Gym/private contest enumeration is outside the main catalog's coverage.
2. Store original response bytes with SHA-256 and retrieval time before normalization. Join statistics by `(contestId,index)`, never by name. Upserts preserve existing statements and references.
3. Fetch public HTML statement pages subject to robots and access restrictions. The job worker uses each canonical problemset URL independently so every stored problem receives its own durable checkpoint. Parse text, examples, limits and related editorial links. Preserve source raw HTML. A challenge page is a collection failure, never a valid empty statement.
4. Supplement with `open-r1/codeforces` at pinned revision. Import only descriptive columns; match the canonical ID against the official catalog. Unmatched rows are not invented as official current catalog entries. Source kind, revision, row hash and aliases remain attached. These are imported statements, not freshly verified HTML.
5. For references, request contest submission pages in bounded batches. Accept only verdict `OK` and C++ language candidates. Store submission metadata first. Fetch source from its public submission page separately. Missing source is `metadata_only`; it never increments source coverage. API verdict is evidence at collection time, not a mathematical proof, not author provenance, and not independent local validation.
6. Read all problems and references in one SQLite read transaction, then freeze deterministic JSONL to an immutable content-addressed filename. Atomically replace the manifest only after the entire JSONL is present; read the filename from the manifest. Counts and split statistics come from the same in-memory snapshot. Preserve original data separately from model inputs. Do not mutate a frozen artifact in a published experiment.

## Performance and failure model

An OS file lock enforces one network collector per data directory, global minimum 2.2 seconds between CF requests, cache 24 hours, fixed HTTPS origin, bounded retry/backoff for transport errors, 429 and 5xx. Cache bytes must match their recorded hash and an API response must have status OK before reuse. 401/403, challenges and robots disallow are surfaced. No proxy rotation or restriction bypass. Reference selection reuses each contest page for multiple targets. HTML scales with available pages and cannot be made arbitrarily fast without violating upstream constraints.

Each job has stable selected IDs, durable processed-item state, status, counts, timestamps, config and event log. A restart pauses inflight jobs only after acquiring ownership. Isolated problem failures do not discard later targets; exhausted network retries stop the job to avoid repeating a system-wide outage. Source-page restrictions preserve AC metadata and continue other targets. The optional metadata-only mode never requests source HTML. Resume retries unfinished, failed and partial work; already stored successful content is idempotent. A job's completed count means processed targets, not successful reference downloads. Bounded reference scans can miss older AC submissions; report the page cap and source coverage. Canonical-URL cache holds the latest response mapping; old raw blobs remain immutable, and frozen records preserve the exact source hash they used.

## Evaluation protocol required for a paper

- Freeze catalog, import revision, parser version and all filtering criteria. Report exclusions, unrated problems, interactive/output-only tasks and missingness by rating/topic/year.
- Review statement conversion, formulas, whitespace, images and non-standard formats. Plain text import can lose mathematical formatting; original URLs/raw source remain necessary audit evidence.
- Split globally before filtering by joining all problems in each contest, declared alias contest IDs, and whitespace-normalized exact descriptions. Hash each connected component’s minimum contest ID with the fixed seed. This prevents known aliases and exact descriptions from crossing splits. Report realized split sizes and assignment hash from the manifest; 80/10/10 is a hash target, not an exact or rating-stratified quota. New aliases may merge groups, so freeze assignments per experiment. Semantic clones and pretraining contamination remain unaddressed.
- Report model name/version, sampling seed, temperature, token budget, tool access, prompt hash, retries, timeout, cost and generation time. Keep editorial, accepted source and private test data out of prompts.
- Pin problem-specific validator/generator/checker versions and test seeds. Validate all reference programs against each frozen testset. Use a brute-force oracle on small cases and independent references where feasible. Measure wrong-solution rejection, not only correct-solution acceptance.
- Separate code compile, execution, checker and infrastructure failures. Report pass@k stratified by rating and test coverage, with confidence intervals and paired comparisons.
- If authorized external submissions become possible, report a paired confusion matrix: local AC vs CF AC, local AC vs CF non-AC, local non-AC vs CF AC, both non-AC. Preserve time, language ID, submission URL and exact source hash.

## Limitations

A source marked AC on Codeforces can depend on a compiler/platform, limits, checker, or historical test set. A local test suite that accepts that source can still be weak or wrong. Universal automatic generation of complete tests from arbitrary statements is not solved by this collector. Local runtime is not comparable to Codeforces timing without controlled calibration. Public problem contamination in LLM pretraining cannot be excluded by a random split. Dataset availability and upstream access can change.

## Sources

- https://codeforces.com/apiHelp — public API and request limits.
- https://codeforces.com/apiHelp/methods — available endpoints; no public submit method listed.
- https://codeforces.com/apiHelp/objects — raw field definitions.
- https://huggingface.co/datasets/open-r1/codeforces — supplemental corpus.
- https://codeforces.com/blog/entry/121114 — compiler command lines; not an assertion of host equivalence.
