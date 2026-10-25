"""Audit raw integrity, missingness and potential duplicates. Does not claim semantic correctness."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpbench.store import Store, digest, now
from cpbench.export import assign_splits, coverage

p = argparse.ArgumentParser()
p.add_argument("--data", default="data")
p.add_argument("--output", default="audit.json")
a = p.parse_args()
s = Store(a.data)
groups = defaultdict(list)
aliases = []
editorials = 0
interactive = 0
broken = []
hashes = set()
rows = assign_splits(s.snapshot_records())
for r in rows:
    st = r["statement"]
    for pr in r["provenance"].values():
        if pr.get("sha256"):
            hashes.add(pr["sha256"])
    if st:
        imported = st.get("imported_reference") or {}
        if imported.get("provenance", {}).get("sha256"):
            hashes.add(imported["provenance"]["sha256"])
        if st.get("content_sha256"):
            groups[st["content_sha256"]].append(r["id"])
        if st.get("aliases"):
            aliases.append({"id": r["id"], "aliases": st["aliases"]})
        if st.get("provenance", {}).get("sha256"):
            hashes.add(st["provenance"]["sha256"])
        editorials += bool(st.get("editorial") or imported.get("editorial"))
        interactive += bool(st.get("interaction_detected"))
    for ref in r["references"]:
        for field in ("provenance", "source_provenance"):
            if ref.get(field, {}).get("sha256"):
                hashes.add(ref[field]["sha256"])
        if (
            ref["source"] is not None
            and digest(ref["source"].encode()) != ref["source_sha256"]
        ):
            broken.append({"submission": ref["id"], "issue": "source_hash_mismatch"})
for sha in hashes:
    path = s.root / "raw" / sha
    if not path.exists() or digest(path.read_bytes()) != sha:
        broken.append({"sha256": sha, "issue": "raw_integrity_failure"})
group_splits = defaultdict(set)
for r in rows:
    group_splits[r["split_group"]].add(r["split"])
report = {
    "created_at": now(),
    "coverage": coverage(rows),
    "split_group_count": len({r["split_group"] for r in rows}),
    "group_assignment_conflicts": sum(len(v) > 1 for v in group_splits.values()),
    "raw_hashes_checked": len(hashes),
    "integrity_failures": broken,
    "editorial_count": editorials,
    "interactive_statement_count": interactive,
    "exact_description_duplicate_groups": [
        ids for ids in groups.values() if len(ids) > 1
    ],
    "alias_records": aliases,
    "semantic_deduplication": "not_performed",
    "judge_validation": "not_performed",
}
Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(
    json.dumps(
        {
            k: v
            for k, v in report.items()
            if k
            not in ("coverage", "alias_records", "exact_description_duplicate_groups")
        },
        indent=2,
    )
)
print(
    "Duplicate groups:",
    len(report["exact_description_duplicate_groups"]),
    "Alias records:",
    len(aliases),
)
raise SystemExit(1 if broken else 0)
