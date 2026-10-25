"""Small, reproducible benchmark pipeline and versioned problem-package extension API."""

import importlib.util
import json
import math
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import judge
from .store import canonical, digest, now

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MODEL_VERDICTS = {"AC", "WA", "TLE", "MLE", "RTE", "CE", "OLE", "SECURITY_VIOLATION"}


def source_code(text):
    blocks = re.findall(r"```(?:cpp|c\+\+|cxx)?\s*\n(.*?)```", text, re.S | re.I)
    if blocks:
        if len(blocks) != 1:
            raise ValueError("Expected one C++ code block, not multiple alternatives")
        return blocks[0].strip() + "\n"
    return text.strip() + "\n"


def summarize(rows, expected_ids):
    """Macro pass@1 = mean per-problem success fraction; missing/infra are explicit."""
    by = {pid: [] for pid in expected_ids}
    for row in rows:
        if row.get("verdict") in MODEL_VERDICTS:
            by.setdefault(row["problem_id"], []).append(row)
    rates = [
        sum(r["verdict"] == "AC" for r in rs) / len(rs) for rs in by.values() if rs
    ]
    verdicts = {}
    for r in rows:
        verdicts[r.get("verdict", "PENDING")] = (
            verdicts.get(r.get("verdict", "PENDING"), 0) + 1
        )
    result = dict(
        problem_count=len(expected_ids),
        evaluated_problems=len(rates),
        attempts=len(rows),
        verdicts=verdicts,
        pass_at_1=sum(rates) / len(rates) if rates else None,
        coverage=len(rates) / len(expected_ids) if expected_ids else 0,
        missing_problem_ids=[p for p, rs in by.items() if not rs],
        infrastructure_errors=sum(r.get("verdict") not in MODEL_VERDICTS for r in rows),
        official_codeforces_ac=False,
    )
    result["pass_at_k"] = {}
    for k in [1, 2, 5]:
        values = []
        for rs in by.values():
            n = len(rs)
            c = sum(r["verdict"] == "AC" for r in rs)
            if n >= k:
                values.append(
                    1 - (math.comb(n - c, k) / math.comb(n, k) if n - c >= k else 0)
                )
        if values:
            result["pass_at_k"][str(k)] = {
                "value": sum(values) / len(values),
                "eligible_problems": len(values),
            }
    for field in ["rating", "tags"]:
        groups = {}
        for r in rows:
            values = (
                r.get(field, []) if field == "tags" else [str(r.get(field, "unrated"))]
            )
            for value in values:
                groups.setdefault(value, []).append(r)
        result["by_" + field] = {}
        for key, rs in groups.items():
            valid = {}
            for row in rs:
                if row.get("verdict") in MODEL_VERDICTS:
                    valid.setdefault(row["problem_id"], []).append(row)
            group_rates = [
                sum(r["verdict"] == "AC" for r in attempts) / len(attempts)
                for attempts in valid.values()
            ]
            result["by_" + field][key] = {
                "attempts": len(rs),
                "ac": sum(r.get("verdict") == "AC" for r in rs),
                "evaluated_problems": len(valid),
                "infrastructure_errors": sum(r.get("verdict") not in MODEL_VERDICTS for r in rs),
                "pass_at_1": sum(group_rates) / len(group_rates) if group_rates else None,
            }
    # Wilson interval only for one valid attempt on every evaluated problem.
    if rates and all(len(rs) == 1 for rs in by.values() if rs):
        n = len(rates)
        p = sum(rates) / n
        z = 1.96
        d = 1 + z * z / n
        center = (p + z * z / (2 * n)) / d
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        result["wilson95"] = [max(0, center - half), min(1, center + half)]
    return result


class Lab:
    def __init__(self, store, package_root=None):
        self.store = store
        self.packages = Path(package_root or ROOT / "packages")
        self.frozen = store.root / "testsets"
        self.frozen.mkdir(exist_ok=True)
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cpbench-judge"
        )
        self.lock = threading.RLock()
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS lab_jobs(id TEXT PRIMARY KEY,kind TEXT,state TEXT,request TEXT,result TEXT,created_at TEXT,updated_at TEXT,idempotency_key TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS lab_packages(problem_id TEXT PRIMARY KEY,testset_version TEXT,report TEXT);
            """)
            db.execute(
                "UPDATE lab_jobs SET state='interrupted',result=? WHERE state IN ('queued','running')",
                (
                    canonical(
                        {
                            "verdict": "INFRA_ERROR",
                            "error": "Server restarted; resubmit explicitly",
                        }
                    ),
                ),
            )

    def close(self):
        self.executor.shutdown(wait=True)

    def package(self, pid):
        if not ID.fullmatch(pid):
            raise ValueError("Invalid problem ID")
        path = self.packages / pid
        if not (path / "manifest.json").is_file():
            raise ValueError(
                "No package for this ID. Install a reviewed package first; see docs/BENCHMARK.md"
            )
        manifest = json.loads((path / "manifest.json").read_text())
        if manifest.get("id") != pid or manifest.get("checker") not in {
            "exact_tokens_v1",
            "integer_tokens_v1",
            "yesno_casefold_v1",
        }:
            raise ValueError("Package ID/checker not supported")
        if (
            not 100 <= manifest["time_limit_ms"] <= 10000
            or not 16 <= manifest["memory_limit_mb"] <= 512
        ):
            raise ValueError("Invalid resource limits")
        for file in [
            manifest["generator"],
            manifest["reference"],
            *manifest["mutants"],
        ]:
            if Path(file).name != file or not (path / file).is_file():
                raise ValueError("Package files must be direct children")
        if not manifest["mutants"]:
            raise ValueError("At least one known wrong solution is required")
        return path, manifest

    def fingerprint(self, pid):
        path, m = self.package(pid)
        files = ["manifest.json", m["generator"], m["reference"], *m["mutants"]]
        hashes = {name: digest((path / name).read_bytes()) for name in files}
        # Shared reviewed implementation is part of the testset definition.
        hashes["cpbench/generators.py"] = digest(
            (ROOT / "cpbench/generators.py").read_bytes()
        )
        record = self.store.problem(pid, include_source=False) or {}
        statement = record.get("statement") or {}
        hashes["statement"] = digest(
            canonical(
                {
                    key: statement.get(key)
                    for key in (
                        "description",
                        "input_format",
                        "output_format",
                        "note",
                        "examples",
                    )
                }
            ).encode()
        )
        hashes["upstream_sources"] = [
            (r["id"], r["source_sha256"])
            for r in record.get("references", [])
            if r.get("source_sha256")
        ]
        return digest(canonical(hashes).encode())

    def list_packages(self):
        result = []
        for file in sorted(self.packages.glob("*/manifest.json")):
            try:
                path, m = self.package(file.parent.name)
                with self.store.connect() as db:
                    row = db.execute(
                        "SELECT * FROM lab_packages WHERE problem_id=?", (m["id"],)
                    ).fetchone()
                report = json.loads(row["report"]) if row else None
                ready = bool(
                    report
                    and report.get("passed")
                    and report.get("package_sha256") == self.fingerprint(m["id"])
                )
                result.append(
                    dict(
                        m,
                        ready=ready,
                        testset_version=row["testset_version"] if ready else None,
                        validation=report,
                    )
                )
            except (ValueError, KeyError) as exc:
                result.append(
                    {"id": file.parent.name, "ready": False, "error": str(exc)}
                )
        return result

    def load_testset(self, pid, version=None):
        use_current = not version
        if not version:
            with self.store.connect() as db:
                row = db.execute(
                    "SELECT testset_version FROM lab_packages WHERE problem_id=?",
                    (pid,),
                ).fetchone()
            if not row:
                raise ValueError("Generate and validate this problem first")
            version = row[0]
        if not re.fullmatch(r"[0-9a-f]{64}", version):
            raise ValueError("Invalid testset version")
        path = self.frozen / (version + ".json")
        if not path.is_file():
            raise ValueError("Unknown frozen testset")
        raw = path.read_bytes()
        if digest(raw) != version:
            raise ValueError("Frozen testset integrity check failed")
        data = json.loads(raw)
        if data["manifest"]["id"] != pid or not data["validation"]["passed"]:
            raise ValueError("Testset not validated for this problem")
        if use_current and data["validation"].get("package_sha256") != self.fingerprint(
            pid
        ):
            raise ValueError(
                "Package, statement or reference sources changed; generate and validate again"
            )
        return version, data

    def list_jobs(self, kind=None):
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT * FROM lab_jobs WHERE (? IS NULL OR kind=?) ORDER BY created_at DESC LIMIT 100",
                (kind, kind),
            ).fetchall()
        return [self.decode(r, brief=True) for r in rows]

    @staticmethod
    def decode(row, brief=False):
        r = dict(row)
        r["request"] = json.loads(r["request"])
        r["result"] = json.loads(r["result"]) if r["result"] else None
        if brief:
            r.pop("request", None)
            if r["result"] and "tests" in r["result"]:
                r["result"] = {
                    k: v
                    for k, v in r["result"].items()
                    if k not in ("tests", "compile")
                }
        return r

    def get(self, jid):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM lab_jobs WHERE id=?", (jid,)).fetchone()
        if not row:
            raise ValueError("Unknown job")
        return self.decode(row)

    def update(self, jid, state, result=None):
        with self.store.connect() as db:
            db.execute(
                "UPDATE lab_jobs SET state=?,result=?,updated_at=? WHERE id=?",
                (state, canonical(result) if result is not None else None, now(), jid),
            )

    def enqueue(self, kind, request, key=None):
        with self.lock:
            with self.store.connect() as db:
                if key:
                    previous = db.execute(
                        "SELECT * FROM lab_jobs WHERE idempotency_key=?", (key,)
                    ).fetchone()
                    if previous:
                        if previous["kind"] != kind or previous["request"] != canonical(
                            request
                        ):
                            raise ValueError(
                                "Idempotency key already used for a different request"
                            )
                        return self.decode(previous)
                if (
                    db.execute(
                        "SELECT count(*) FROM lab_jobs WHERE state IN ('queued','running')"
                    ).fetchone()[0]
                    >= 50
                ):
                    raise ValueError("Queue full; wait for current work")
                jid = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO lab_jobs VALUES(?,?,?,?,?,?,?,?)",
                    (jid, kind, "queued", canonical(request), None, now(), now(), key),
                )
            self.executor.submit(self.work, jid, kind, request)
            return self.get(jid)

    def work(self, jid, kind, request):
        self.update(jid, "running")
        try:
            if kind == "generate":
                result = self.generate(**request)
            elif kind == "submission":
                result = self.submit(**request)
            elif kind == "benchmark":
                result = self.benchmark(jid, **request)
            else:
                raise ValueError("Unknown job kind")
            self.update(jid, "complete", result)
        except Exception as exc:
            self.update(
                jid,
                "failed",
                {"verdict": "INFRA_ERROR", "error": f"{type(exc).__name__}: {exc}"},
            )

    def generate(self, problem_id, seed=42, count=32):
        path, manifest = self.package(problem_id)
        spec = importlib.util.spec_from_file_location(
            "reviewed_generator_" + problem_id, path / manifest["generator"]
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests = module.generate(seed, count)
        if canonical(tests) != canonical(module.generate(seed, count)):
            raise ValueError("Generator is not deterministic for the given seed")
        if not tests or len(tests) > 512:
            raise ValueError("Each pilot package requires 1..512 tests")
        if len(canonical(tests).encode()) > 8 * 1024**2:
            raise ValueError("Testset exceeds 8 MiB pilot limit")
        for case in tests:
            module.validate(case["input"])
        record = self.store.problem(problem_id)
        samples = (record or {}).get("statement") or {}
        samples = samples.get("examples", [])
        if not samples:
            raise ValueError(
                "Need source statement with samples in corpus before validation"
            )
        sample_cases = []
        for sample in samples:
            module.validate(sample["input"])
            sample_cases.append(
                dict(
                    input=sample["input"],
                    output=sample["output"],
                    category="statement_sample",
                    brute_verified=False,
                )
            )
        tests = sample_cases + tests
        if len(tests) > 512 or len(canonical(tests).encode()) > 8 * 1024**2:
            raise ValueError("Testset including samples exceeds pilot budget")
        info = judge.environment()
        if not info["available"]:
            raise ValueError(info["error"])
        reference = judge.evaluate(
            (path / manifest["reference"]).read_text(),
            tests,
            manifest,
            info["image_id"],
        )
        mutant_results = []
        for file in manifest["mutants"]:
            r = judge.evaluate(
                (path / file).read_text(), tests, manifest, info["image_id"]
            )
            mutant_results.append(
                dict(
                    file=file,
                    verdict=r["verdict"],
                    detected=r["verdict"] in {"WA", "TLE", "MLE", "RTE", "OLE"},
                    first_failure=next(
                        (
                            t["index"]
                            for t in r.get("tests", [])
                            if t["verdict"] != "AC"
                        ),
                        None,
                    ),
                )
            )
        upstream_references = []
        candidates = [
            r
            for r in (record or {}).get("references", [])
            if r.get("source") and r.get("verdict") == "OK"
        ]
        for ref in candidates[:5]:
            tested = judge.evaluate(ref["source"], tests, manifest, info["image_id"])
            upstream_references.append(
                dict(
                    submission_id=ref["id"],
                    url=ref["url"],
                    source_sha256=ref["source_sha256"],
                    verdict=tested["verdict"],
                    result=tested,
                )
            )
        report = dict(
            passed=reference["verdict"] == "AC"
            and all(r["detected"] for r in mutant_results)
            and all(r["verdict"] == "AC" for r in upstream_references)
            and any(t.get("brute_verified") for t in tests),
            reference_verdict=reference["verdict"],
            reference=reference,
            mutants=mutant_results,
            brute_verified=sum(t.get("brute_verified", False) for t in tests),
            sample_count=len(samples),
            test_count=len(tests),
            package_sha256=self.fingerprint(problem_id),
            environment=reference.get("environment"),
            local_ac_only=True,
            validated_at=now(),
            upstream_references=upstream_references,
            upstream_available=len(candidates),
            upstream_checked=len(upstream_references),
            tests_sha256=digest(canonical(tests).encode()),
        )
        if not report["passed"]:
            return dict(
                problem_id=problem_id,
                validation=report,
                error="Validation failed; no benchmark enabled",
            )
        data = dict(
            schema_version=1,
            statement_snapshot={
                key: ((record or {}).get("statement") or {}).get(key)
                for key in (
                    "description",
                    "input_format",
                    "output_format",
                    "note",
                    "examples",
                )
            },
            manifest=manifest,
            seed=seed,
            count=count,
            tests=tests,
            validation=report,
        )
        raw = canonical(data).encode()
        version = digest(raw)
        (self.frozen / (version + ".json")).write_bytes(raw)
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO lab_packages VALUES(?,?,?)",
                (problem_id, version, canonical(report)),
            )
        return dict(
            problem_id=problem_id,
            testset_version=version,
            bytes=len(raw),
            validation=report,
        )

    def submit(self, problem_id, source_code, testset_version=None, **extra):
        version, pack = self.load_testset(problem_id, testset_version)
        result = judge.evaluate(
            source_code,
            pack["tests"],
            pack["manifest"],
            pack["validation"]["environment"]["image_id"],
        )
        result.update(
            problem_id=problem_id,
            testset_version=version,
            rating=pack["manifest"]["rating"],
            tags=pack["manifest"]["tags"],
            local_ac_only=True,
        )
        return result

    def prompts(self, ids):
        output = []
        for pid in ids:
            version, pack = self.load_testset(pid)
            p = self.store.problem(pid)
            s = pack.get("statement_snapshot") or p.get("statement") or {}
            parts = [
                f"Solve {p['name']}. Write a complete GNU C++20 program using stdin/stdout. Return only one C++ code block."
            ]
            for field, label in [
                ("description", "Problem"),
                ("input_format", "Input"),
                ("output_format", "Output"),
                ("note", "Note"),
            ]:
                if s.get(field):
                    parts.append(label + ":\n" + s[field])
            for sample in s.get("examples", []):
                parts.append(
                    "Sample input:\n"
                    + sample["input"]
                    + "\nSample output:\n"
                    + sample["output"]
                )
            prompt = "\n\n".join(parts)
            output.append(
                dict(
                    problem_id=pid,
                    testset_version=version,
                    prompt=prompt,
                    prompt_sha256=digest(prompt.encode()),
                    language="cpp20",
                )
            )
        return output

    def benchmark(self, jid, name, rows, problem_ids, model_metadata=None):
        results = []
        for row in rows:
            result = self.submit(
                row["problem_id"], row["source_code"], row["testset_version"]
            )
            result["sample_id"] = row["sample_id"]
            results.append(result)
            self.update(
                jid,
                "running",
                dict(
                    name=name,
                    completed=len(results),
                    total=len(rows),
                    rows=results,
                    summary=summarize(results, problem_ids),
                ),
            )
        return dict(
            name=name,
            model_metadata=model_metadata or {},
            rows=results,
            summary=summarize(results, problem_ids),
            protocol="offline-jsonl-v1",
            created_at=now(),
            limitations=[
                "Public pilot: possible training contamination",
                "Local test AC is not Codeforces AC",
                "Selected pilot is not a representative CP benchmark",
            ],
        )
