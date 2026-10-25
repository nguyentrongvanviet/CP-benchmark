"""Export current source and a small, local-only six-problem pilot archive."""

import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpbench.store import Store

IDS = ("4A", "1A", "158A", "189A", "455A", "474B")


def source_files():
    for folder in ("cpbench", "scripts", "tests", "docs", "packages", "judge", "examples"):
        for p in sorted((ROOT / folder).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                yield p, p.relative_to(ROOT).as_posix()
    for p in sorted((ROOT / "dist").rglob("*")):
        if p.is_file() and ("vendor" in p.parts or p.suffix in (".js", ".css", ".html")):
            yield p, p.relative_to(ROOT).as_posix()
    for pattern in ("README.md", "requirements*.txt", "start.command", ".gitignore"):
        for p in ROOT.glob(pattern):
            yield p, p.name


def archive(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for p, name in files:
            out.write(p, name)
    print(f"{path.name}: {path.stat().st_size:,} bytes")


def main():
    files = list(source_files())
    archive(ROOT / "dist/cpbench-source.zip", files)
    source = sqlite3.connect(ROOT / "data/cpbench.sqlite")
    source.row_factory = sqlite3.Row
    with tempfile.TemporaryDirectory(prefix="cpbench-pilot-") as tmp:
        stage = Path(tmp)
        store = Store(stage / "data")
        evidence = set()
        versions = []
        with store.connect() as dest:
            for table in ("lab_packages", "lab_jobs"):
                dest.execute(source.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0])
            for table, column in (("problems", "id"), ("reference_solutions", "problem_id"), ("lab_packages", "problem_id")):
                rows = source.execute(f"SELECT * FROM {table} WHERE {column} IN ({','.join('?' for _ in IDS)})", IDS)
                for row in rows:
                    dest.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})", tuple(row))
                    for value in row:
                        if isinstance(value, str):
                            evidence.update(re.findall(r"\b[0-9a-f]{64}\b", value))
                    if table == "lab_packages":
                        versions.append(row["testset_version"])
            for row in source.execute("SELECT * FROM fetches"):
                if row["sha256"] in evidence:
                    dest.execute("INSERT INTO fetches VALUES (?,?,?,?,?,?)", tuple(row))
        store_files = [(stage / "data/cpbench.sqlite", "data/cpbench.sqlite")]
        for sha in sorted(evidence):
            p = ROOT / "data/raw" / sha
            if p.is_file():
                store_files.append((p, "data/raw/" + sha))
        for version in versions:
            p = ROOT / "data/testsets" / (version + ".json")
            store_files.append((p, "data/testsets/" + p.name))
        note = stage / "PILOT-START.md"
        note.write_text("""# Small pilot bundle

Contains only six problems and their current frozen testsets, sources and linked raw evidence. No account keys, cookies, entire catalog, or Docker image.

Install Python dependencies, start Docker, then run:

```sh
python -m pip install -r requirements.txt
docker build -t cpbench-judge:v1 judge
python -m cpbench serve --port 8765
```

Open http://127.0.0.1:8765/#benchmark. On a new machine, use **Sinh phiên bản mới** for each problem: old reports pin the original image content ID, which is deliberately not replaced silently by a new build. Existing reports remain historical evidence. See docs/BENCHMARK.md for extension, API and evaluation protocol.

Source authors retain their rights. This is a local research bundle, not a grant of redistribution rights. Reports named pipeline-selftest are harness checks, not LLM performance measurements.
""")
        archive(ROOT.parent / "CPBench-pilot.zip", files + store_files + [(note, note.name)])
    source.close()


if __name__ == "__main__":
    main()
