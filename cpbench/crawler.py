"""Public Codeforces collection: global throttling, cache, bounded retry, checkpoints."""

import json
import threading
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from .parser import BlockedError, RobotsDisallowed, parse_source, parse_statement
from .store import Store, canonical, digest, now


class CollectionPaused(Exception):
    """Cooperative cancellation at request/retry boundaries."""


class CFClient:
    def __init__(self, store, interval=2.2):
        self.store = store
        self.interval = max(2.2, interval)
        self.lock = threading.Lock()
        self.last = 0.0
        self.robots = None
        self.cancel_check = None
        self.client = httpx.Client(
            timeout=45,
            follow_redirects=False,
            headers={
                "User-Agent": "CPBenchResearch/0.1 (public corpus collection; 1 request per 2.2s)",
                "Accept-Language": "en",
            },
        )

    def _checkpoint(self):
        if self.cancel_check and not self.cancel_check():
            raise CollectionPaused()

    def _sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._checkpoint()
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))

    def get(self, path, params=None, cached=True):
        self._checkpoint()
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only fixed Codeforces paths are allowed")
        url = (
            "https://codeforces.com"
            + path
            + ("?" + urlencode(params) if params else "")
        )
        if cached:
            with self.store.connect() as db:
                row = db.execute(
                    "SELECT * FROM fetches WHERE url=? AND status=200", (url,)
                ).fetchone()
            if (
                row
                and (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(row["fetched_at"])
                ).total_seconds()
                < 86400
            ):
                raw_path = self.store.root / "raw" / row["sha256"]
                cached_body = raw_path.read_bytes() if raw_path.exists() else b""
                valid = bool(cached_body) and digest(cached_body) == row["sha256"]
                if valid and path.startswith("/api/"):
                    try:
                        valid = json.loads(cached_body).get("status") == "OK"
                    except (ValueError, AttributeError):
                        valid = False
                if valid and (b"Just a moment..." in cached_body[:1000]):
                    valid = False
                if valid:
                    return cached_body, dict(row)
        for attempt in range(4):
            self._checkpoint()
            try:
                # Includes request start scheduling, so threads cannot burst.
                with self.lock:
                    self._sleep(max(0, self.interval - (time.monotonic() - self.last)))
                    self.last = time.monotonic()
                    response = self.client.get(url)
            except httpx.TransportError:
                if attempt == 3:
                    raise
                self._sleep(2**attempt)
                continue
            prov = self.store.evidence(
                url,
                response.content,
                response.status_code,
                response.headers.get("content-type", ""),
            )
            if (
                response.status_code in (401, 403)
                or b"Just a moment..." in response.content[:1000]
            ):
                raise BlockedError(
                    f"Codeforces restricted access (HTTP {response.status_code}); manual access/import required"
                )
            if response.status_code == 429 or response.status_code >= 500:
                retry = response.headers.get("retry-after", "")
                delay = (
                    min(120, float(retry))
                    if retry.isdigit()
                    else min(60, 4 * 2**attempt)
                )
                if attempt < 3:
                    self._sleep(delay)
                    continue
            response.raise_for_status()
            if path.startswith("/api/"):
                body = response.json()
                if body.get("status") != "OK":
                    if "limit" in body.get("comment", "").lower() and attempt < 3:
                        self._sleep(4 * 2**attempt)
                        continue
                    raise RuntimeError(body.get("comment", "API FAILED"))
            return response.content, prov
        raise RuntimeError("Retries exhausted")

    def api(self, method, params=None, cached=True):
        body, prov = self.get("/api/" + method, params, cached)
        return json.loads(body), prov

    def html(self, path):
        if self.robots is None:
            body, _ = self.get("/robots.txt")
            robot = urllib.robotparser.RobotFileParser()
            robot.parse(body.decode(errors="replace").splitlines())
            self.robots = robot
        if not self.robots.can_fetch(
            "CPBenchResearch", "https://codeforces.com" + path
        ):
            raise RobotsDisallowed("robots.txt disallows this HTML path")
        body, prov = self.get(path, {"locale": "en"})
        return body.decode("utf-8", errors="replace"), prov


class Crawler:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or CFClient(store)

    def sync_metadata(self):
        problems, pp = self.client.api("problemset.problems", cached=False)
        contests, cp = self.client.api("contest.list", {"gym": "false"}, cached=False)
        return self.store.ingest_catalog(problems, contests, pp, cp)

    def statement(self, pid):
        p = self.store.problem(pid)
        html, prov = self.client.html(
            f"/problemset/problem/{p['contest_id']}/{p['index']}"
        )
        self.store.save_statement(pid, parse_statement(html, prov))

    def statements(self, contest_id, target_ids):
        """One public contest page contains all its statements; avoid N HTML requests."""
        from bs4 import BeautifulSoup

        try:
            html, prov = self.client.html(f"/contest/{contest_id}/problems")
        except RobotsDisallowed:
            # Respect route-specific restrictions: each canonical problemset URL
            # is checked independently by html() before any network request.
            for pid in target_ids:
                self.statement(pid)
            return
        soup = BeautifulSoup(html, "html.parser")
        roots = soup.select(".problem-statement")
        if not roots:
            raise BlockedError(
                "Contest page has no statement roots; access challenge or unsupported format"
            )
        by_index = {}
        for root in roots:
            title = root.select_one(".title")
            if title:
                index = title.get_text(strip=True).split(".", 1)[0]
                by_index[index] = root
        for pid in target_ids:
            p = self.store.problem(pid)
            root = by_index.get(p["index"])
            if root is None:
                raise BlockedError(
                    f"Statement {pid} missing from contest page; manual review required"
                )
            self.store.save_statement(pid, parse_statement(str(root), prov))

    def references(
        self,
        contest_id,
        target_ids,
        max_pages=20,
        checkpoint=None,
        metadata_only=False,
        on_item=None,
    ):
        """Collect AC evidence for every target, even if public source routes are denied."""
        remaining = set(target_ids)
        exhausted = False
        for page in range(max_pages):
            if checkpoint and not checkpoint():
                return False
            body, prov = self.client.api(
                "contest.status",
                {"contestId": contest_id, "from": page * 1000 + 1, "count": 1000},
            )
            rows = body["result"]
            for submission in rows:
                if checkpoint and not checkpoint():
                    return False
                p = submission.get("problem", {})
                pid = f"{p.get('contestId')}{p.get('index')}"
                if (
                    pid not in remaining
                    or submission.get("verdict") != "OK"
                    or "++" not in submission.get("programmingLanguage", "")
                ):
                    continue
                sid = submission["id"]
                record = dict(
                    submission,
                    problem_id=pid,
                    url=f"https://codeforces.com/contest/{contest_id}/submission/{sid}",
                    provenance=prov,
                    reference_kind="accepted_community_submission",
                    official_editorial=False,
                    verification="codeforces_api_verdict_at_collection",
                    local_validation="not_run",
                )
                with self.store.connect() as db:
                    db.execute(
                        "INSERT OR IGNORE INTO reference_solutions VALUES(?,?,?,?,?)",
                        (sid, pid, canonical(record), None, None),
                    )
                    db.execute(
                        "UPDATE problems SET reference_status='metadata_only' WHERE id=? AND reference_status!='complete'",
                        (pid,),
                    )
                outcome, error = "done", None
                if not metadata_only:
                    try:
                        html, source_prov = self.client.html(
                            f"/contest/{contest_id}/submission/{sid}"
                        )
                        source = parse_source(html)
                        record["source_provenance"] = source_prov
                        with self.store.connect() as db:
                            db.execute(
                                "UPDATE reference_solutions SET record=?,source=?,source_sha256=? WHERE submission_id=?",
                                (
                                    canonical(record),
                                    source,
                                    digest(source.encode()),
                                    sid,
                                ),
                            )
                            db.execute(
                                "UPDATE problems SET reference_status='complete' WHERE id=?",
                                (pid,),
                            )
                    except (BlockedError, httpx.HTTPError, ValueError) as exc:
                        # An inaccessible source does not erase the official AC metadata,
                        # and must not prevent finding evidence for unrelated targets.
                        outcome, error = "partial", str(exc)
                        record["source_collection_error"] = error
                        with self.store.connect() as db:
                            db.execute(
                                "UPDATE reference_solutions SET record=? WHERE submission_id=? AND source IS NULL",
                                (canonical(record), sid),
                            )
                remaining.remove(pid)
                if on_item:
                    on_item(pid, outcome, error)
            if not remaining or len(rows) < 1000:
                exhausted = len(rows) < 1000
                break
        for pid in sorted(remaining):
            if on_item:
                on_item(
                    pid,
                    "partial",
                    "No accepted C++ candidate in available pages"
                    if exhausted
                    else f"Page cap reached ({max_pages}); older submissions not scanned",
                )
        return True
