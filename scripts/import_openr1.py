"""Import descriptive columns from a pinned Open R1 release using HTTP ranges.
No hidden tests or generated checkers are imported or executed.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ssl
import certifi
import fsspec
import httpx
import pyarrow.parquet as pq
from cpbench.store import Store, canonical, digest, now

COLUMNS = [
    "id",
    "aliases",
    "description",
    "input_format",
    "output_format",
    "interaction_format",
    "note",
    "examples",
    "editorial",
    "time_limit",
    "memory_limit",
    "input_mode",
    "title",
]
parser = argparse.ArgumentParser()
parser.add_argument("--revision", required=True)
parser.add_argument("--data", default="data")
parser.add_argument("--max-shards", type=int, default=0)
args = parser.parse_args()
if not re.fullmatch("[0-9a-f]{40}", args.revision):
    parser.error("Use a full pinned Hugging Face commit SHA")
store = Store(args.data)
repo = "open-r1/codeforces"
with httpx.Client(timeout=60, follow_redirects=True) as client:
    response = client.get(
        f"https://huggingface.co/api/datasets/{repo}/tree/{args.revision}/data"
    )
    response.raise_for_status()
    tree = response.json()
    listing = store.evidence(str(response.url), response.content)
fs = fsspec.filesystem(
    "https",
    block_size=64 * 1024,
    client_kwargs={"trust_env": True},
    ssl=ssl.create_default_context(cafile=certifi.where()),
)
files = [x for x in tree if x["path"].endswith(".parquet")]
if args.max_shards:
    files = files[: args.max_shards]
count = 0
for item in files:
    path = item["path"]
    checkpoint = store.root / (
        "openr1-" + args.revision + "-" + Path(path).stem + ".done"
    )
    if checkpoint.exists():
        print("Already imported", path, flush=True)
        continue
    url = f"https://huggingface.co/datasets/{repo}/resolve/{args.revision}/{path}"
    print("Reading selected columns", path, flush=True)
    with fs.open(url, "rb") as f:
        rows = pq.ParquetFile(f).read(columns=COLUMNS, use_threads=False).to_pylist()
    for r in rows:
        match = re.fullmatch(r"(\d+)/([A-Za-z]\d*)", r["id"])
        if not match:
            continue
        pid = match[1] + match[2]
        existing = store.problem(pid)
        if not existing or existing["statement_status"] == "complete":
            continue
        evidence = store.evidence(
            f"{url}#id={r['id']}",
            canonical(r).encode(),
            content_type="application/json",
        )
        statement = {k: r.get(k) for k in COLUMNS if k not in ("id", "aliases")}
        statement.update(
            source_kind="open_r1_import",
            provenance=dict(
                evidence,
                dataset=repo,
                revision=args.revision,
                shard=path,
                upstream_file_sha256=(item.get("lfs") or {}).get("oid"),
                license="CC-BY-4.0",
                original_url=existing["url"],
                directly_verified=False,
            ),
            aliases=r.get("aliases"),
            editorial_urls=[],
            content_sha256=digest((r.get("description") or "").encode()),
            interaction_detected=bool(r.get("interaction_format"))
            or r.get("input_mode") == "interactive",
            time_limit=f"{r.get('time_limit')} seconds",
            memory_limit=f"{r.get('memory_limit')} MB",
        )
        store.save_statement(pid, statement, "imported")
        count += 1
    checkpoint.write_text(
        canonical({"imported_at": now(), "rows": len(rows), "listing": listing})
    )
    store.event(
        None,
        f"Open R1 imported {path}: {len(rows)} rows at revision {args.revision[:12]}",
    )
    print("Imported total", count, flush=True)
print(json.dumps(store.stats(), ensure_ascii=False))
