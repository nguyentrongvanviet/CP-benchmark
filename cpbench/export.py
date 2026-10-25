"""Snapshot-consistent exports and deterministic splits of connected problem groups."""

import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from .store import canonical, digest, now, SCHEMA_VERSION

SPLIT_SEED = "cpbench-v1"


def split_for(group, seed=SPLIT_SEED):
    n = int(digest(f"{seed}:{group}".encode())[:8], 16) % 100
    return "train" if n < 80 else "validation" if n < 90 else "test"


def assign_splits(rows):
    """Connect contests, declared aliases and exact normalized descriptions globally.

    Compute BEFORE filtering: filtered exports must preserve full-corpus assignments.
    This is a conservative leakage guard, not a semantic duplicate detector.
    """
    parents = {}

    def find(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[max(a, b)] = min(a, b)

    descriptions = {}
    for p in rows:
        contest = p["contest_id"]
        find(contest)
        s = p.get("statement") or {}
        versions = [s, s.get("imported_reference") or {}]
        for version in versions:
            for alias in version.get("aliases") or []:
                match = re.fullmatch(r"(\d+)/?([A-Za-z][A-Za-z0-9]*)", str(alias))
                if match:
                    # Keep even aliases outside this snapshot: known equivalence matters.
                    union(contest, int(match[1]))
            text = " ".join((version.get("description") or "").split())
            if text:
                sha = digest(text.encode())
                if sha in descriptions:
                    union(contest, descriptions[sha])
                else:
                    descriptions[sha] = contest
    for p in rows:
        group = find(p["contest_id"])
        p["split_group"] = str(group)
        p["split"] = split_for(group)
    return rows


def matches(p, filters):
    q = (filters.get("q") or "").casefold()
    if (
        q
        and q
        not in " ".join(
            [p["id"], p["name"], (p.get("contest") or {}).get("name", "")]
        ).casefold()
    ):
        return False
    rating = p.get("rating")
    for name, fails in [
        ("min_rating", lambda v: rating < v),
        ("max_rating", lambda v: rating > v),
    ]:
        bound = filters.get(name)
        if bound is not None and (rating is None or fails(bound)):
            return False
    if filters.get("tag") and filters["tag"] not in p["tags"]:
        return False
    status = filters.get("status")
    if status == "available":
        return p["statement_status"] in ("complete", "imported")
    return not status or p["statement_status"] == status


def records(store, filters=None, prompts_only=False):
    rows = assign_splits(store.snapshot_records())
    for record in rows:
        if not matches(record, filters or {}):
            continue
        if prompts_only:
            s = record["statement"]
            if not s:
                continue
            # Allowlist prevents editorial/reference/private-test leakage into prompts.
            record = {
                k: record[k]
                for k in ("id", "name", "url", "rating", "split", "split_group")
            }
            record["statement"] = {
                k: s.get(k)
                for k in (
                    "description",
                    "input_format",
                    "output_format",
                    "interaction_format",
                    "time_limit",
                    "memory_limit",
                    "examples",
                    "note",
                )
            }
        yield record


def atomic_write(path, body):
    """Publish a complete file via replace; readers never see partial bytes."""
    fd, temporary = tempfile.mkstemp(prefix=".cpbench-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def coverage(rows):
    ratings = Counter(p["rating"] for p in rows if p["rating"] is not None)
    tags = Counter(t for p in rows for t in p["tags"])
    return dict(
        total=len(rows),
        rated=sum(ratings.values()),
        unrated=sum(p["rating"] is None for p in rows),
        statements=dict(Counter(p["statement_status"] for p in rows)),
        references=sum(
            any(r.get("source") is not None for r in p["references"]) for p in rows
        ),
        reference_metadata=sum(bool(p["references"]) for p in rows),
        histogram=[dict(rating=r, count=c) for r, c in sorted(ratings.items())],
        tags=[
            dict(tag=t, count=c)
            for t, c in sorted(tags.items(), key=lambda item: (-item[1], item[0]))
        ],
        updated_at=max((p["updated_at"] for p in rows), default=None),
        benchmark_ready=0,
    )


def freeze(store, destination):
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    rows = list(records(store))
    body = ("\n".join(canonical(r) for r in rows) + ("\n" if rows else "")).encode()
    sha = digest(body)
    filename = f"corpus-{sha}.jsonl"
    # Content-addressed file is immutable. Manifest replacement is the commit point.
    atomic_write(path / filename, body)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now(),
        "sha256": sha,
        "file": filename,
        "records": len(rows),
        "split": {
            "method": "Connected components of contest IDs, declared aliases and whitespace-normalized exact descriptions; sha256(seed:minimum_contest_id) modulo 100",
            "seed": SPLIT_SEED,
            "target_ratios": [80, 10, 10],
            "actual_counts": dict(Counter(p["split"] for p in rows)),
            "groups": len({p["split_group"] for p in rows}),
            "assignments_sha256": digest(
                canonical(
                    [(p["id"], p["split_group"], p["split"]) for p in rows]
                ).encode()
            ),
            "warning": "Freeze assignments per experiment: new aliases can merge groups. Semantic clones and pretraining contamination still require review; ratings are not stratified.",
        },
        "coverage": coverage(rows),
        "judge_implemented": False,
        "sources": [
            "https://codeforces.com/apiHelp",
            "https://huggingface.co/datasets/open-r1/codeforces",
        ],
    }
    atomic_write(
        path / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
    )
    return manifest


def web_snapshot(store, destination):
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    rows = store.snapshot_records()
    problems, chunks = [], {}
    for p in rows:
        problems.append(
            dict(
                **{
                    k: p[k]
                    for k in (
                        "id",
                        "contest_id",
                        "index",
                        "name",
                        "rating",
                        "tags",
                        "url",
                        "type",
                        "statement_status",
                        "reference_status",
                    )
                },
                contest_name=(p["contest"] or {}).get("name", ""),
                contest_start=(p["contest"] or {}).get("startTimeSeconds"),
                solved_count=p["statistics"].get("solvedCount", 0),
            )
        )
        chunks.setdefault(p["contest_id"] // 100, {})[p["id"]] = p
    details = path / "problems"
    details.mkdir(exist_ok=True)
    for chunk, data in chunks.items():
        atomic_write(details / f"{chunk}.json", canonical(data).encode())
    snapshot = dict(
        mode="snapshot", generated_at=now(), stats=coverage(rows), problems=problems
    )
    # Static deployment packages the completed directory as one release.
    atomic_write(path / "snapshot.json", canonical(snapshot).encode())
    with store.connect() as db:
        jobs = [
            dict(r)
            for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100")
        ]
        for job in jobs:
            job["outcomes"] = dict(
                db.execute(
                    "SELECT state,COUNT(*) FROM job_items WHERE job_id=? GROUP BY state",
                    (job["id"],),
                )
            )
            job.update(
                succeeded=job["outcomes"].get("done", 0),
                partial=job["outcomes"].get("partial", 0),
                failed=job["outcomes"].get("failed", 0),
            )
        events = [
            dict(r)
            for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")
        ]
    atomic_write(
        path / "activity.json", canonical(dict(jobs=jobs, events=events)).encode()
    )
