"""Durable, single-owner collection with per-problem outcomes and resumable failures."""

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import httpx
from .crawler import Crawler, CollectionPaused
from .locking import CollectorLock
from .parser import BlockedError
from .store import canonical, now


class JobManager:
    def __init__(self, store):
        self.store = store
        self.ownership = CollectorLock(store.root).acquire()
        self.crawler = Crawler(store)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crawler")
        self.guard = threading.RLock()
        self.futures = {}
        self.closed = False
        with store.connect() as db:
            db.execute(
                "UPDATE jobs SET state='paused', error='Process restarted; resume from checkpoint' WHERE state IN ('running','queued')"
            )

    def close(self):
        if self.closed:
            return
        self.closed = True
        with self.store.connect() as db:
            db.execute(
                "UPDATE jobs SET state='paused' WHERE state IN ('running','queued')"
            )
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.crawler.client.client.close()
        self.ownership.close()

    def get(self, jid):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row:
                return None
            counts = dict(
                db.execute(
                    "SELECT state,COUNT(*) FROM job_items WHERE job_id=? GROUP BY state",
                    (jid,),
                ).fetchall()
            )
        return dict(
            row,
            outcomes=counts,
            succeeded=counts.get("done", 0),
            partial=counts.get("partial", 0),
            failed=counts.get("failed", 0),
        )

    def list(self):
        with self.store.connect() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 100"
                )
            ]
        return [self.get(jid) for jid in ids]

    def items(self, jid, offset=0, limit=100):
        with self.store.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM job_items WHERE job_id=? ORDER BY item_id LIMIT ? OFFSET ?",
                    (jid, limit, offset),
                )
            ]

    def assert_idle(self):
        if any(not f.done() for f in self.futures.values()):
            raise ValueError("Current request is finishing; retry shortly")
        with self.store.connect() as db:
            if db.execute(
                "SELECT 1 FROM jobs WHERE state IN ('running','queued')"
            ).fetchone():
                raise ValueError("A collector job is already active; pause it first")

    def create(self, kind, config):
        if kind not in ("metadata", "statements", "references"):
            raise ValueError("Unknown collector kind")
        with self.guard:
            self.assert_idle()
            filters = {
                k: config[k]
                for k in ("q", "min_rating", "max_rating", "tag", "status")
                if config.get(k) is not None
            }
            items = (
                self.store.list_problems(**filters, limit=100000)["items"]
                if kind != "metadata"
                else []
            )
            if kind == "statements":
                statuses = (
                    ("complete",)
                    if config.get("verify_imported")
                    else ("complete", "imported")
                )
                items = [p for p in items if p["statement_status"] not in statuses]
            if kind == "references":
                # Load contest state once instead of opening a DB connection per candidate.
                with self.store.connect() as db:
                    finished = {
                        r[0]
                        for r in db.execute(
                            "SELECT DISTINCT contest_id FROM problems WHERE json_extract(record,'$.contest.phase')='FINISHED'"
                        )
                    }
                excluded = (
                    ("complete", "metadata_only")
                    if config.get("metadata_only")
                    else ("complete",)
                )
                items = [
                    p
                    for p in items
                    if p["reference_status"] not in excluded
                    and p["contest_id"] in finished
                ]
            if config.get("limit"):
                items = items[: config["limit"]]
            jid = uuid.uuid4().hex[:12]
            with self.store.connect() as db:
                db.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        jid,
                        kind,
                        "queued",
                        canonical(config),
                        len(items) if kind != "metadata" else 2,
                        0,
                        None,
                        now(),
                        now(),
                    ),
                )
                db.executemany(
                    "INSERT INTO job_items(job_id,item_id) VALUES(?,?)",
                    [(jid, p["id"]) for p in items],
                )
            self.futures[jid] = self.pool.submit(self.run, jid)
            return self.get(jid)

    def active(self, jid):
        if self.closed:
            return False
        # Cancellation runs several times per second; avoid recounting every item.
        with self.store.connect() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()
        return bool(row and row["state"] == "running")

    def set_state(self, jid, state, error=None):
        with self.store.connect() as db:
            db.execute(
                "UPDATE jobs SET state=?,error=?,updated_at=? WHERE id=?",
                (state, error, now(), jid),
            )

    def pause(self, jid):
        with self.guard:
            if self.get(jid)["state"] not in ("running", "queued"):
                raise ValueError("Job is not active")
            self.set_state(jid, "paused")
        self.store.event(jid, "Pause requested; current request may finish")

    def resume(self, jid):
        with self.guard:
            if self.get(jid)["state"] not in (
                "paused",
                "blocked",
                "failed",
                "completed_with_errors",
            ):
                raise ValueError("Job is not resumable")
            self.assert_idle()
            # Partial sources remain visible; retry them only on an explicit resume.
            with self.store.connect() as db:
                db.execute(
                    "UPDATE job_items SET state='pending',error=NULL WHERE job_id=? AND state!='done'",
                    (jid,),
                )
                db.execute(
                    "UPDATE jobs SET completed=(SELECT COUNT(*) FROM job_items WHERE job_id=? AND state='done') WHERE id=?",
                    (jid, jid),
                )
            self.set_state(jid, "queued")
            self.futures[jid] = self.pool.submit(self.run, jid)

    def outcome(self, jid, pid, state, error=None):
        with self.store.connect() as db:
            db.execute(
                "UPDATE job_items SET state=?,error=?,attempts=attempts+1 WHERE job_id=? AND item_id=?",
                (state, error, jid, pid),
            )
            db.execute(
                "UPDATE jobs SET completed=(SELECT COUNT(*) FROM job_items WHERE job_id=? AND state IN ('done','partial','failed')),updated_at=? WHERE id=?",
                (jid, now(), jid),
            )
        self.store.event(
            jid,
            f"{pid}: {state}" + (f" — {error}" if error else ""),
            "info" if state == "done" else "warning",
        )

    def run(self, jid):
        with self.guard:
            job = self.get(jid)
            if job["state"] != "queued" or self.closed:
                return
            self.set_state(jid, "running")
        self.store.event(jid, f"Started {job['kind']}")
        config = json.loads(job["config"])
        current = None
        self.crawler.client.cancel_check = lambda: self.active(jid)
        try:
            if job["kind"] == "metadata":
                count = self.crawler.sync_metadata()
                with self.store.connect() as db:
                    db.execute("UPDATE jobs SET completed=2 WHERE id=?", (jid,))
                self.store.event(jid, f"Catalog synchronized: {count} problem records")
            else:
                with self.store.connect() as db:
                    rows = db.execute(
                        "SELECT j.item_id,p.contest_id FROM job_items j JOIN problems p ON p.id=j.item_id WHERE j.job_id=? AND j.state='pending' ORDER BY p.contest_id DESC,p.problem_index",
                        (jid,),
                    ).fetchall()
                if job["kind"] == "statements":
                    for row in rows:
                        if not self.active(jid):
                            return
                        current = row["item_id"]
                        try:
                            # Canonical URLs are always checked against robots.txt.
                            self.crawler.statement(current)
                            self.outcome(jid, current, "done")
                        except BlockedError:
                            raise  # Stop systemic restrictions, never bypass them.
                        except httpx.TransportError as exc:
                            self.outcome(jid, current, "failed", str(exc))
                            raise  # Exhausted network retries are a collector-wide outage.
                        except httpx.HTTPStatusError as exc:
                            self.outcome(jid, current, "failed", str(exc))
                            if (
                                exc.response.status_code == 429
                                or exc.response.status_code >= 500
                            ):
                                raise
                        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                            self.outcome(jid, current, "failed", str(exc))
                            continue  # An isolated problem must not discard a corpus job.
                else:
                    contests = {}
                    for row in rows:
                        contests.setdefault(row["contest_id"], []).append(
                            row["item_id"]
                        )
                    for cid, ids in contests.items():
                        if not self.active(jid):
                            return
                        try:
                            done = self.crawler.references(
                                cid,
                                ids,
                                config.get("max_pages", 20),
                                checkpoint=lambda: self.active(jid),
                                metadata_only=config.get("metadata_only", False),
                                on_item=lambda pid, status, error=None: self.outcome(
                                    jid, pid, status, error
                                ),
                            )
                            if not done:
                                return
                        except BlockedError:
                            raise
                        except httpx.TransportError:
                            raise
                        except httpx.HTTPStatusError as exc:
                            if (
                                exc.response.status_code == 429
                                or exc.response.status_code >= 500
                            ):
                                raise
                            pending = {
                                i["item_id"]
                                for i in self.items(jid, limit=100000)
                                if i["state"] == "pending"
                            }
                            for pid in ids:
                                if pid in pending:
                                    self.outcome(jid, pid, "failed", str(exc))
                        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                            for pid in ids:
                                if any(
                                    i["item_id"] == pid and i["state"] == "pending"
                                    for i in self.items(jid, limit=100000)
                                ):
                                    self.outcome(jid, pid, "failed", str(exc))
            with self.guard:
                if self.active(jid):
                    summary = self.get(jid)
                    self.set_state(
                        jid,
                        "completed_with_errors"
                        if summary["partial"] or summary["failed"]
                        else "completed",
                    )
        except CollectionPaused:
            return
        except BlockedError as exc:
            if current:
                self.outcome(jid, current, "blocked", str(exc))
            if self.active(jid):
                self.set_state(jid, "blocked", str(exc))
            self.store.event(jid, str(exc), "warning")
        except Exception as exc:
            if self.active(jid):
                self.set_state(jid, "failed", str(exc))
            self.store.event(jid, str(exc), "error")
        finally:
            self.crawler.client.cancel_check = None
