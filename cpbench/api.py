"""Local API. Bind to loopback; crawler is usable independently of the web UI."""

import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from .store import Store, canonical
from .jobs import JobManager
from .export import records
from .lab import Lab
from .lab_api import routes


class CrawlRequest(BaseModel):
    kind: Literal["metadata", "statements", "references"] = "metadata"
    q: str = ""
    min_rating: int | None = Field(default=None, ge=0, le=4000)
    max_rating: int | None = Field(default=None, ge=0, le=4000)
    tag: str = ""
    status: str = ""
    limit: int = Field(default=0, ge=0, le=100000)
    metadata_only: bool = False
    verify_imported: bool = False
    max_pages: int = Field(default=20, ge=1, le=1000)

    @model_validator(mode="after")
    def bounds(self):
        if (
            self.min_rating is not None
            and self.max_rating is not None
            and self.min_rating > self.max_rating
        ):
            raise ValueError("Minimum rating must not exceed maximum rating")
        return self


def create_app(data_dir=None):
    store = Store(data_dir)
    manager = JobManager(store)
    lab = Lab(store)

    @asynccontextmanager
    async def lifespan(app):
        yield
        lab.close()
        manager.close()

    app = FastAPI(
        title="CPBench Corpus API",
        version="0.3.0",
        lifespan=lifespan,
        description="Corpus collection and independently validated local C++ benchmark. No automatic Codeforces submissions.",
    )
    app.state.store = store
    app.state.manager = manager
    app.state.lab = lab
    app.include_router(routes(lab, manager))

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # No wildcard CORS; reject cross-site mutation / DNS-rebinding against the local agent.
        if request.url.hostname not in ("localhost", "127.0.0.1", "testserver"):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Local API only"}, status_code=403)
        origin = request.headers.get("origin")
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": "Cross-origin writes are disabled; open the local UI"},
                status_code=403,
            )
        if request.method in ("POST", "PUT", "PATCH"):
            from fastapi.responses import JSONResponse

            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024:
                    return JSONResponse(
                        {"detail": "Request exceeds 5 MiB pilot limit"}, status_code=413
                    )
            request._body = bytes(body)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "local",
            "judge": True,
            "codeforces_submit": False,
        }

    @app.get("/api/catalog")
    def catalog():
        return {
            "stats": dict(
                store.stats(),
                benchmark_ready=sum(p["ready"] for p in lab.list_packages()),
            ),
            "problems": store.list_problems(limit=100000)["items"],
        }

    @app.get("/api/stats")
    def stats():
        return dict(
            store.stats(), benchmark_ready=sum(p["ready"] for p in lab.list_packages())
        )

    @app.get("/api/problems")
    def problems(
        q: str = "",
        min_rating: int | None = None,
        max_rating: int | None = None,
        tag: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ):
        return store.list_problems(
            q,
            min_rating,
            max_rating,
            tag,
            status,
            min(max(limit, 1), 500),
            max(offset, 0),
        )

    @app.get("/api/problems/{pid}")
    def problem(pid: str):
        result = store.problem(pid)
        if not result:
            raise HTTPException(404, "Unknown problem ID")
        try:
            version, frozen = lab.load_testset(pid)
            checked = {
                r["submission_id"]: r
                for r in frozen["validation"].get("upstream_references", [])
            }
            for reference in result.get("references", []):
                test = checked.get(reference["id"])
                if test and test["source_sha256"] == reference.get("source_sha256"):
                    reference["local_validation"] = {
                        "verdict": test["verdict"],
                        "testset_version": version,
                    }
            result.update(
                benchmark_ready=True,
                judge_status="local_testset_validated",
                testset_version=version,
            )
        except ValueError:
            result.update(benchmark_ready=False, judge_status="package_not_validated")
        statement = result.get("statement")
        if (
            statement
            and not statement.get("rich_html")
            and statement.get("source_kind") == "codeforces_html"
        ):
            sha = statement.get("provenance", {}).get("sha256", "")
            if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha):
                raw = store.root / "raw" / sha
                if raw.is_file():
                    from bs4 import BeautifulSoup

                    root = BeautifulSoup(raw.read_bytes(), "html.parser").select_one(
                        ".problem-statement"
                    )
                    if root:
                        statement["rich_html"] = str(root)
        return result

    @app.get("/api/jobs")
    def jobs():
        return manager.list()

    @app.get("/api/jobs/{jid}/items")
    def job_items(jid: str, offset: int = 0, limit: int = 100):
        if not manager.get(jid):
            raise HTTPException(404, "Unknown job")
        return manager.items(jid, max(0, offset), max(1, min(500, limit)))

    @app.post("/api/jobs", status_code=202)
    def create_job(body: CrawlRequest):
        try:
            return manager.create(body.kind, body.model_dump(exclude={"kind"}))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/jobs/{jid}/{action}")
    def control(jid: str, action: Literal["pause", "resume"]):
        if not manager.get(jid):
            raise HTTPException(404, "Unknown job")
        try:
            getattr(manager, action)(jid)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return manager.get(jid)

    @app.get("/api/events")
    def events():
        with store.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")
            ]

    @app.get("/api/export")
    def export(
        q: str = "",
        min_rating: int | None = None,
        max_rating: int | None = None,
        tag: str = "",
        status: str = "",
        prompts_only: bool = False,
    ):
        filters = dict(
            q=q, min_rating=min_rating, max_rating=max_rating, tag=tag, status=status
        )
        return StreamingResponse(
            (canonical(r) + "\n" for r in records(store, filters, prompts_only)),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": 'attachment; filename="cpbench-corpus.jsonl"'
            },
        )

    app.mount(
        "/",
        StaticFiles(
            directory=Path(__file__).resolve().parent.parent / "dist", html=True
        ),
        name="ui",
    )
    return app
