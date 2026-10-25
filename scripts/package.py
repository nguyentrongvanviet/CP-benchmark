"""Create download archives. Source excludes runtime data, credentials and Site identity."""

from pathlib import Path
import zipfile
import json

ROOT = Path(__file__).resolve().parents[1]


def write_zip(target, files):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, name in files:
            z.write(path, name)
    print(target.name, target.stat().st_size, "bytes")


manifest_path = ROOT / "frozen/manifest.json"
manifest = json.loads(manifest_path.read_text())
corpus_path = ROOT / "frozen" / manifest["file"]
corpus = [(manifest_path, "manifest.json"), (corpus_path, manifest["file"])]
corpus += [
    (ROOT / "docs/ATTRIBUTION.md", "ATTRIBUTION.md"),
    (ROOT / "docs/METHODOLOGY.md", "METHODOLOGY.md"),
]
write_zip(ROOT / "dist/corpus.zip", corpus)
from package_pilot import source_files

write_zip(ROOT / "dist/cpbench-source.zip", list(source_files()))
