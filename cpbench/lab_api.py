"""REST contract for asynchronous judging, frozen prompts, and offline model evaluations."""

import json
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr
from .lab import Lab, source_code, ROOT
from . import judge
from .account import import_account, normalize_browser_source
from .store import canonical, digest, now


class Generate(BaseModel):
    problem_id: str
    seed: int = Field(42, ge=0, le=2**32 - 1)
    count: int = Field(32, ge=1, le=128)


class Submission(BaseModel):
    problem_id: str
    source_code: str = Field(min_length=1, max_length=256000)
    testset_version: str | None = None
    language: str = "cpp20"
    idempotency_key: str | None = Field(None, max_length=128)


class Benchmark(BaseModel):
    name: str = Field("Offline model run", min_length=1, max_length=128)
    jsonl: str = Field(min_length=1, max_length=4000000)
    problem_ids: list[str] = Field(min_length=1, max_length=50)
    model_metadata: dict = Field(default_factory=dict)


class Account(BaseModel):
    handle: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    count: int = Field(100, ge=1, le=500)
    offset: int = Field(1, ge=1)


class BrowserSource(BaseModel):
    submission_id: int = Field(gt=0)
    source_code: str = Field(min_length=1, max_length=256000)
    observed_url: str


def routes(lab: Lab, manager):
    router = APIRouter()

    @router.get("/api/guide")
    def guide():
        return Response(
            (ROOT / "docs/BENCHMARK.md").read_text(),
            media_type="text/plain; charset=utf-8",
        )

    @router.get("/api/lab")
    def status():
        return {
            "environment": judge.environment(),
            "packages": lab.list_packages(),
            "jobs": lab.list_jobs(),
            "pilot_limit": "512 tests / 8 MiB per testset",
            "codeforces_submit": False,
        }

    @router.post("/api/testsets", status_code=202)
    def generate(body: Generate):
        try:
            lab.package(body.problem_id)
            return lab.enqueue("generate", body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @router.get("/api/lab/jobs/{jid}")
    def job(jid: str):
        try:
            return lab.get(jid)
        except ValueError as exc:
            raise HTTPException(404, str(exc))

    @router.get("/api/submissions/{jid}")
    def submission_result(jid: str):
        return job(jid)

    @router.post("/api/submissions", status_code=202)
    def submit(body: Submission):
        try:
            pid = body.problem_id
            if pid.startswith("https://codeforces.com/"):
                match = re.fullmatch(
                    r"https://codeforces\.com/(?:problemset/problem|contest)/(\d+)/(?:problem/)?([A-Za-z]\d*)/?",
                    pid,
                )
                if not match:
                    raise ValueError("Unsupported Codeforces problem URL")
                pid = match[1] + match[2].upper()
            if body.language != "cpp20":
                raise ValueError("Only cpp20 is supported")
            version, _ = lab.load_testset(pid, body.testset_version)
            return lab.enqueue(
                "submission",
                dict(
                    problem_id=pid,
                    source_code=source_code(body.source_code),
                    testset_version=version,
                ),
                body.idempotency_key,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @router.get("/api/benchmark/prompts")
    def prompts(ids: str):
        try:
            selected = list(dict.fromkeys(ids.split(",")))
            if len(selected) > 50:
                raise ValueError("Select at most 50 problems")
            return Response(
                "".join(
                    json.dumps(p, ensure_ascii=False) + "\n"
                    for p in lab.prompts(selected)
                ),
                media_type="application/x-ndjson",
                headers={
                    "Content-Disposition": 'attachment; filename="cpbench-prompts.jsonl"'
                },
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @router.post("/api/benchmark/runs", status_code=202)
    def benchmark(body: Benchmark):
        try:
            ids = list(dict.fromkeys(body.problem_ids))
            versions = {p: lab.load_testset(p)[0] for p in ids}
            rows = []
            keys = set()
            for line in body.jsonl.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                pid = row["problem_id"]
                if pid not in versions:
                    raise ValueError(f"{pid} not in selected evaluation set")
                sid = str(row.get("sample_id", "0"))
                if (pid, sid) in keys:
                    raise ValueError("Duplicate problem_id/sample_id")
                keys.add((pid, sid))
                code = row.get("source_code", row.get("code"))
                if not isinstance(code, str) or not code.strip() or len(code) > 256000:
                    raise ValueError("Each row needs source_code (max 256 KB)")
                version = row.get("testset_version") or versions[pid]
                lab.load_testset(pid, version)
                if version != versions[pid]:
                    raise ValueError(
                        "Row uses a different frozen testset; regenerate prompts or submit via /api/submissions with the old version"
                    )
                rows.append(
                    dict(
                        problem_id=pid,
                        sample_id=sid,
                        source_code=source_code(code),
                        testset_version=version,
                    )
                )
            if not rows or len(rows) > 100:
                raise ValueError("Import 1..100 code samples per pilot run")
            if len(json.dumps(body.model_metadata)) > 10000:
                raise ValueError("Model metadata exceeds 10 KB")
            request = dict(
                name=body.name,
                rows=rows,
                problem_ids=ids,
                model_metadata=body.model_metadata,
            )
            request["model_metadata"]["prompt_manifest"] = lab.prompts(ids)
            return lab.enqueue("benchmark", request)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, str(exc))

    @router.get("/api/benchmark/runs/{jid}/export")
    def export(jid: str):
        data = job(jid)
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="cpbench-{jid}.json"'
            },
        )

    @router.post("/api/problems/{pid}/refresh-statement")
    def refresh_statement(pid: str):
        if not lab.store.problem(pid):
            raise HTTPException(404, "Unknown problem")
        try:
            with manager.guard:
                manager.assert_idle()
                manager.crawler.client.cancel_check = None
                manager.crawler.statement(pid)
            return {"problem_id": pid, "status": "complete"}
        except Exception as exc:
            raise HTTPException(
                422, f"Statement collection failed: {type(exc).__name__}"
            ) from None

    @router.post("/api/packages/{pid}/reference-candidate")
    def reference_candidate(pid: str):
        problem = lab.store.problem(pid)
        if not problem:
            raise HTTPException(404, "Unknown problem")
        try:
            with manager.guard:
                manager.assert_idle()
                manager.crawler.client.cancel_check = None
                manager.crawler.references(
                    problem["contest_id"], [pid], max_pages=1, metadata_only=True
                )
            return lab.store.problem(pid)["references"]
        except Exception as exc:
            raise HTTPException(
                422, f"Reference metadata request failed: {type(exc).__name__}"
            )

    @router.post("/api/references/import")
    def browser_source(body: BrowserSource):
        with lab.store.connect() as db:
            row = db.execute(
                "SELECT * FROM reference_solutions WHERE submission_id=?",
                (body.submission_id,),
            ).fetchone()
        if not row:
            raise HTTPException(
                422, "Fetch official accepted metadata for this submission first"
            )
        record = json.loads(row["record"])
        if record.get("verdict") != "OK" or body.observed_url != record.get("url"):
            raise HTTPException(
                422, "Source URL must match the accepted submission metadata"
            )
        normalized = normalize_browser_source(body.source_code)
        if row["source"] and normalize_browser_source(row["source"]) != normalized:
            raise HTTPException(
                409,
                "A different source is already bound to this submission; refusing overwrite",
            )
        evidence = lab.store.evidence(
            body.observed_url, body.source_code.encode(), content_type="text/x-c++src"
        )
        record.update(
            source_origin="browser_assisted_import",
            source_provenance=evidence,
            source_binding="browser_observation_user_attested",
            source_normalization="prettify_nbsp_blank_lines_only",
            local_validation="not_run",
        )
        with lab.store.connect() as db:
            db.execute(
                "UPDATE reference_solutions SET record=?,source=?,source_sha256=? WHERE submission_id=?",
                (
                    canonical(record),
                    normalized,
                    digest(normalized.encode()),
                    body.submission_id,
                ),
            )
            db.execute(
                "UPDATE problems SET reference_status='complete' WHERE id=?",
                (row["problem_id"],),
            )
        return dict(
            problem_id=row["problem_id"],
            submission_id=body.submission_id,
            source_sha256=digest(normalized.encode()),
            status="source_imported",
        )

    @router.post("/api/account/import")
    def account(body: Account):
        try:
            return import_account(
                lab.store,
                manager.crawler.client,
                body.handle,
                body.api_key.get_secret_value(),
                body.api_secret.get_secret_value(),
                body.count,
                body.offset,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    return router
