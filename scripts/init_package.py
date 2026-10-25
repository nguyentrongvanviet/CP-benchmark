"""Scaffold a NEW package for any corpus ID; never pretend arbitrary generators are correct."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpbench.store import Store
from cpbench.lab import ID

p = argparse.ArgumentParser()
p.add_argument("problem_id")
p.add_argument("--data", default="data")
args = p.parse_args()
if not ID.fullmatch(args.problem_id):
    p.error("Invalid ID")
record = Store(args.data).problem(args.problem_id)
if not record:
    p.error("Import the problem metadata and statement first")
root = Path(__file__).resolve().parents[1] / "packages" / args.problem_id
if root.exists():
    p.error("Package exists; refusing to overwrite")
root.mkdir()
manifest = dict(
    schema_version=1,
    id=args.problem_id,
    name=record["name"],
    rating=record["rating"],
    tags=record["tags"],
    version="0.1.0",
    generator="generator.py",
    checker="exact_tokens_v1",
    time_limit_ms=2000,
    memory_limit_mb=256,
    reference="reference.cpp",
    mutants=["wrong.cpp"],
    reference_origin="not_configured",
    url=record["url"],
    scope="custom",
)
(root / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
)
(
    root / "generator.py"
).write_text('''"""TRUSTED developer extension. Review before installing; never paste scraped code here."""
def validate(text):
    raise NotImplementedError("Implement all problem constraints")

def generate(seed, count):
    # Return [{"input": "...", "output": "...", "category": "boundary", "brute_verified": False}]
    # Derive expected output independently; cross-check small cases with a brute oracle.
    raise NotImplementedError("Implement a problem-specific generator and independent oracle")
''')
(root / "reference.cpp").write_text(
    "// Add an attributed reference solution. Not an accepted-code claim.\n#error Reference not configured\n"
)
(root / "wrong.cpp").write_text(
    "// Add a plausible, compilable, known-wrong mutation.\n#error Mutation not configured\n"
)
(root / "statement.json").write_text(
    json.dumps(record.get("statement"), ensure_ascii=False, indent=2)
)
print(root)
