"""SQLite persistence and content-addressed raw evidence. No network in this module."""

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.1.0"


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("CPBENCH_DATA", "data"))
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "raw").mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS problems (
                id TEXT PRIMARY KEY, contest_id INTEGER, problem_index TEXT,
                name TEXT NOT NULL, rating INTEGER, tags TEXT NOT NULL,
                record TEXT NOT NULL, statement TEXT, statement_status TEXT NOT NULL DEFAULT 'missing',
                reference_status TEXT NOT NULL DEFAULT 'missing', updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS problems_rating ON problems(rating);
            CREATE INDEX IF NOT EXISTS problems_contest ON problems(contest_id);
            CREATE TABLE IF NOT EXISTS reference_solutions (
                submission_id INTEGER PRIMARY KEY, problem_id TEXT NOT NULL,
                record TEXT NOT NULL, source TEXT, source_sha256 TEXT);
            CREATE TABLE IF NOT EXISTS fetches (
                url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, fetched_at TEXT NOT NULL,
                status INTEGER NOT NULL, content_type TEXT, size INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                config TEXT NOT NULL, total INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,
                error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS job_items (
                job_id TEXT NOT NULL, item_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                error TEXT, PRIMARY KEY(job_id,item_id));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, job_id TEXT, at TEXT NOT NULL, level TEXT NOT NULL,
                message TEXT NOT NULL);
            """)

            # Additive, idempotent migration: preserve databases created by v0.1.
            columns = {row[1] for row in db.execute("PRAGMA table_info(job_items)")}
            if "attempts" not in columns:
                db.execute(
                    "ALTER TABLE job_items ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
                )
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "cpbench.sqlite", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def evidence(
        self, url, body, status=200, content_type="application/json", fetched_at=None
    ):
        sha = digest(body)
        path = self.root / "raw" / sha
        if not path.exists() or digest(path.read_bytes()) != sha:
            fd, temporary = tempfile.mkstemp(prefix=".raw-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(body)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        record = dict(
            url=url,
            sha256=sha,
            fetched_at=fetched_at or now(),
            status=status,
            content_type=content_type,
            size=len(body),
        )
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO fetches VALUES (:url,:sha256,:fetched_at,:status,:content_type,:size)",
                record,
            )
        return record

    def ingest_catalog(
        self, problemset, contests, problem_provenance, contest_provenance
    ):
        if problemset.get("status") != "OK" or contests.get("status") != "OK":
            raise ValueError("Codeforces API did not return OK")
        contest_map = {c["id"]: c for c in contests["result"]}
        statistics = {
            (p.get("contestId"), p["index"]): p
            for p in problemset["result"]["problemStatistics"]
        }
        with self.connect() as db:
            for p in problemset["result"]["problems"]:
                if "contestId" not in p:
                    continue
                cid, index = p["contestId"], p["index"]
                pid = f"{cid}{index}"
                record = dict(
                    schema_version=SCHEMA_VERSION,
                    id=pid,
                    contest_id=cid,
                    index=index,
                    name=p["name"],
                    rating=p.get("rating"),
                    tags=p.get("tags", []),
                    type=p.get("type"),
                    points=p.get("points"),
                    problemset_name=p.get("problemsetName"),
                    url=f"https://codeforces.com/problemset/problem/{cid}/{index}",
                    contest_url=f"https://codeforces.com/contest/{cid}",
                    submit_url=f"https://codeforces.com/contest/{cid}/submit/{index}",
                    contest=contest_map.get(cid),
                    statistics=statistics.get((cid, index), {}),
                    raw_problem=p,
                    provenance={
                        "problemset": problem_provenance,
                        "contest": contest_provenance,
                    },
                    judge_status="not_implemented",
                    benchmark_ready=False,
                )
                db.execute(
                    """INSERT INTO problems(id,contest_id,problem_index,name,rating,tags,record,updated_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,rating=excluded.rating,tags=excluded.tags,record=excluded.record,updated_at=excluded.updated_at""",
                    (
                        pid,
                        cid,
                        index,
                        p["name"],
                        p.get("rating"),
                        canonical(p.get("tags", [])),
                        canonical(record),
                        now(),
                    ),
                )
        return len(problemset["result"]["problems"])

    def problem(self, pid, include_source=True):
        with self.connect() as db:
            row = db.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
            if not row:
                return None
            result = json.loads(row["record"])
            result.update(
                schema_version=SCHEMA_VERSION,
                statement=json.loads(row["statement"]) if row["statement"] else None,
                statement_status=row["statement_status"],
                reference_status=row["reference_status"],
                updated_at=row["updated_at"],
            )
            refs = db.execute(
                "SELECT * FROM reference_solutions WHERE problem_id=? ORDER BY submission_id",
                (pid,),
            ).fetchall()
            result["references"] = [
                dict(
                    json.loads(r["record"]),
                    source=r["source"] if include_source else None,
                    source_sha256=r["source_sha256"],
                )
                for r in refs
            ]
            return result

    def list_problems(
        self,
        q="",
        min_rating=None,
        max_rating=None,
        tag="",
        status="",
        limit=50,
        offset=0,
    ):
        clauses, values = ["1=1"], []
        if q:
            clauses.append(
                "(id LIKE ? OR name LIKE ? OR json_extract(record,'$.contest.name') LIKE ?)"
            )
            values += [f"%{q}%"] * 3
        for op, val in [(">=", min_rating), ("<=", max_rating)]:
            if val is not None:
                clauses.append(f"rating {op} ?")
                values.append(val)
        if tag:
            clauses.append(
                "EXISTS(SELECT 1 FROM json_each(problems.tags) WHERE value=?)"
            )
            values.append(tag)
        if status == "available":
            clauses.append("statement_status IN ('complete','imported')")
        elif status:
            clauses.append("statement_status=?")
            values.append(status)
        where = " AND ".join(clauses)
        with self.connect() as db:
            total = db.execute(
                f"SELECT COUNT(*) FROM problems WHERE {where}", values
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM problems WHERE {where} ORDER BY contest_id DESC, problem_index LIMIT ? OFFSET ?",
                values + [limit, offset],
            ).fetchall()
        items = []
        for row in rows:
            p = json.loads(row["record"])
            items.append(
                dict(
                    id=p["id"],
                    contest_id=p["contest_id"],
                    index=p["index"],
                    name=p["name"],
                    rating=p["rating"],
                    tags=p["tags"],
                    contest_name=(p["contest"] or {}).get("name", ""),
                    contest_start=(p["contest"] or {}).get("startTimeSeconds"),
                    solved_count=p["statistics"].get("solvedCount", 0),
                    url=p["url"],
                    statement_status=row["statement_status"],
                    reference_status=row["reference_status"],
                    type=p["type"],
                )
            )
        return {"items": items, "total": total}

    def save_statement(self, pid, statement, status="complete"):
        with self.connect() as db:
            previous = db.execute(
                "SELECT statement,statement_status FROM problems WHERE id=?", (pid,)
            ).fetchone()
            if previous and previous["statement"] and status == "complete":
                old = json.loads(previous["statement"])
                imported = (
                    old
                    if previous["statement_status"] == "imported"
                    else old.get("imported_reference")
                )
                if imported:
                    # Keep secondary editorial/aliases and their provenance when
                    # replacing imported text with a verified primary statement.
                    statement = dict(statement, imported_reference=imported)
            db.execute(
                "UPDATE problems SET statement=?,statement_status=?,updated_at=? WHERE id=?",
                (canonical(statement), status, now(), pid),
            )

    def event(self, job_id, message, level="info"):
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(job_id,at,level,message) VALUES(?,?,?,?)",
                (job_id, now(), level, message),
            )

    def stats(self):
        with self.connect() as db:
            db.execute("BEGIN")
            total = db.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
            rated = db.execute(
                "SELECT COUNT(*) FROM problems WHERE rating IS NOT NULL"
            ).fetchone()[0]
            statements = dict(
                db.execute(
                    "SELECT statement_status, COUNT(*) FROM problems GROUP BY statement_status"
                ).fetchall()
            )
            refs = db.execute(
                "SELECT COUNT(DISTINCT problem_id) FROM reference_solutions WHERE source IS NOT NULL"
            ).fetchone()[0]
            reference_metadata = db.execute(
                "SELECT COUNT(DISTINCT problem_id) FROM reference_solutions"
            ).fetchone()[0]
            histogram = [
                dict(r)
                for r in db.execute(
                    "SELECT rating,COUNT(*) AS count FROM problems WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating"
                )
            ]
            tags = [
                dict(r)
                for r in db.execute(
                    "SELECT value AS tag,COUNT(*) AS count FROM problems,json_each(problems.tags) GROUP BY value ORDER BY COUNT(*) DESC"
                )
            ]
            last = db.execute("SELECT MAX(updated_at) FROM problems").fetchone()[0]
            evidence = db.execute("SELECT COUNT(*) FROM fetches").fetchone()[0]
        return dict(
            total=total,
            rated=rated,
            unrated=total - rated,
            statements=statements,
            references=refs,
            reference_metadata=reference_metadata,
            histogram=histogram,
            tags=tags,
            updated_at=last,
            evidence_count=evidence,
            benchmark_ready=0,
        )

    def snapshot_records(self):
        """Read all records and references from one SQLite snapshot (no N+1 queries)."""
        with self.connect() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT * FROM problems ORDER BY contest_id DESC,problem_index"
            ).fetchall()
            refs = db.execute(
                "SELECT * FROM reference_solutions ORDER BY submission_id"
            ).fetchall()
        by_problem = {}
        for ref in refs:
            by_problem.setdefault(ref["problem_id"], []).append(
                dict(
                    json.loads(ref["record"]),
                    source=ref["source"],
                    source_sha256=ref["source_sha256"],
                )
            )
        result = []
        for row in rows:
            record = json.loads(row["record"])
            record.update(
                schema_version=SCHEMA_VERSION,
                statement=json.loads(row["statement"]) if row["statement"] else None,
                statement_status=row["statement_status"],
                reference_status=row["reference_status"],
                updated_at=row["updated_at"],
                references=by_problem.get(row["id"], []),
            )
            result.append(record)
        return result
