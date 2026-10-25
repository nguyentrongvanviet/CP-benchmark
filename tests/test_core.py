import pytest
from fastapi.testclient import TestClient
from cpbench.store import Store, canonical, digest
from cpbench.parser import parse_statement, parse_source, BlockedError
from cpbench.crawler import Crawler, CFClient
from cpbench.export import freeze, records, split_for
from cpbench.api import create_app
from cpbench.jobs import JobManager


@pytest.fixture
def seeded(tmp_path):
    s = Store(tmp_path)
    p = {
        "status": "OK",
        "result": {
            "problems": [
                {
                    "contestId": 4,
                    "index": "A",
                    "name": "Example",
                    "rating": 800,
                    "tags": ["math"],
                    "type": "PROGRAMMING",
                },
                {
                    "contestId": 4,
                    "index": "B",
                    "name": "Other",
                    "tags": ["dp"],
                    "type": "PROGRAMMING",
                },
            ],
            "problemStatistics": [{"contestId": 4, "index": "A", "solvedCount": 20}],
        },
    }
    c = {
        "status": "OK",
        "result": [{"id": 4, "name": "Test contest", "phase": "FINISHED"}],
    }
    prov = s.evidence("https://codeforces.com/api/test", canonical(p).encode())
    s.ingest_catalog(p, c, prov, prov)
    return s, p, c, prov


def test_idempotent_sync_preserves_statement(seeded):
    s, p, c, prov = seeded
    s.save_statement("4A", {"description": "persist"})
    p["result"]["problems"][0]["rating"] = 900
    s.ingest_catalog(p, c, prov, prov)
    assert s.stats()["total"] == 2 and s.problem("4A")["rating"] == 900
    assert s.problem("4A")["statement"]["description"] == "persist"


def test_null_rating_and_exact_tag_filter(seeded):
    s, *_ = seeded
    assert s.stats()["unrated"] == 1 and s.list_problems(min_rating=0)["total"] == 1
    assert (
        s.list_problems(tag="math")["total"] == 1
        and s.list_problems(tag="ma")["total"] == 0
    )
    assert s.list_problems(q="' OR 1=1 --")["total"] == 0


def test_evidence_integrity(seeded):
    s, _, _, p = seeded
    assert digest((s.root / "raw" / p["sha256"]).read_bytes()) == p["sha256"]


def test_sample_line_breaks():
    html = '<div class="problem-statement"><div>Statement</div><div class="sample-tests"><div class="sample-test"><div class="input"><pre>1<br>2</pre></div><div class="output"><pre><div class="test-example-line">3</div><div class="test-example-line">4</div></pre></div></div></div></div>'
    p = parse_statement(html, {})
    assert p["description"] == "Statement" and p["examples"] == [
        {"input": "1\n2", "output": "3\n4"}
    ]


@pytest.mark.parametrize(
    "html",
    ["<title>Just a moment...</title>", "<h1>Login</h1>", "<p>Unknown markup</p>"],
)
def test_challenge_not_statement(html):
    with pytest.raises(BlockedError):
        parse_statement(html, {})


def test_source_not_fabricated():
    with pytest.raises(BlockedError):
        parse_source("<html>challenge</html>")
    assert parse_source('<pre id="program-source-text">a &lt; b</pre>') == "a < b"


def test_only_cpp_accepted_reference(seeded):
    s, *_ = seeded

    class Client:
        def api(self, *args):
            base = {
                "problem": {"contestId": 4, "index": "A"},
                "programmingLanguage": "GNU C++17",
                "verdict": "OK",
            }
            return {
                "result": [
                    dict(base, id=1, verdict="WRONG_ANSWER"),
                    dict(base, id=2, programmingLanguage="Python 3"),
                    dict(base, id=3),
                ]
            }, {"sha256": "evidence"}

        def html(self, path):
            assert path.endswith("/3")
            return '<pre id="program-source-text">int main(){}</pre>', {
                "sha256": "source_evidence"
            }

    Crawler(s, Client()).references(4, ["4A"])
    r = s.problem("4A")["references"][0]
    assert r["id"] == 3 and r["official_editorial"] is False
    assert r["source_sha256"] == digest(b"int main(){}")


def test_blocked_source_preserves_ac_metadata(seeded):
    s, *_ = seeded

    class Client:
        def api(self, *args):
            return {
                "result": [
                    {
                        "id": 5,
                        "problem": {"contestId": 4, "index": "A"},
                        "verdict": "OK",
                        "programmingLanguage": "GNU C++20",
                    }
                ]
            }, {}

        def html(self, *args):
            raise BlockedError("403")

    outcomes = []
    assert Crawler(s, Client()).references(
        4, ["4A"], on_item=lambda *x: outcomes.append(x)
    )
    assert outcomes == [("4A", "partial", "403")]
    assert s.problem("4A")["reference_status"] == "metadata_only"
    assert (
        s.problem("4A")["references"][0]["source"] is None
        and s.stats()["references"] == 0
    )


def test_prompt_export_excludes_answers(seeded):
    s, *_ = seeded
    s.save_statement(
        "4A",
        {
            "description": "prompt",
            "editorial": "SECRET",
            "provenance": {"secret": "x"},
            "examples": [],
        },
    )
    out = list(records(s, prompts_only=True))
    assert len(out) == 1 and out[0]["statement"]["description"] == "prompt"
    assert "SECRET" not in canonical(out) and "provenance" not in canonical(out)


def test_reproducible_hash_and_contest_splits(seeded, tmp_path):
    s, *_ = seeded
    a = freeze(s, tmp_path / "one")
    b = freeze(s, tmp_path / "two")
    assert a["sha256"] == b["sha256"]
    assert {p["split"] for p in records(s)} == {split_for(4)}


def test_api_validation_security_and_judge_contract(seeded):
    s, *_ = seeded
    with TestClient(create_app(s.root)) as c:
        assert c.get("/api/problems?min_rating=800").json()["total"] == 1
        assert c.get("/api/problems/missing").status_code == 404
        assert (
            c.post(
                "/api/jobs",
                json={"kind": "references", "min_rating": 2000, "max_rating": 1000},
            ).status_code
            == 422
        )
        assert c.post("/api/submissions", json={}).status_code == 422
        assert (
            c.post(
                "/api/jobs",
                json={"kind": "metadata"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 403


def test_restart_pauses_inflight_jobs(seeded):
    s, *_ = seeded
    with s.connect() as db:
        db.execute(
            "INSERT INTO jobs VALUES('job','statements','running','{}',2,1,NULL,'a','a')"
        )
    m = JobManager(s)
    assert m.get("job")["state"] == "paused" and m.get("job")["completed"] == 1
    m.close()


def test_resume_blocked_job_checkpoint(seeded):
    s, *_ = seeded
    m = JobManager(s)

    def blocked(pid):
        raise BlockedError("restricted")

    m.crawler.statement = blocked
    j = m.create("statements", {"limit": 1})
    m.futures[j["id"]].result(timeout=5)
    assert m.get(j["id"])["state"] == "blocked"
    m.crawler.statement = lambda pid: s.save_statement(
        pid, {"description": "collected"}
    )
    m.resume(j["id"])
    m.futures[j["id"]].result(timeout=5)
    assert m.get(j["id"])["state"] == "completed" and m.get(j["id"])["completed"] == 1
    m.close()


def test_rate_floor_and_fixed_origin(seeded):
    s, *_ = seeded
    c = CFClient(s, interval=0)
    assert c.interval >= 2
    with pytest.raises(ValueError):
        c.get("//evil.example")
    c.client.close()


def test_batch_falls_back_only_to_allowed_canonical_urls(seeded):
    from cpbench.parser import RobotsDisallowed

    s, *_ = seeded
    seen = []

    class Client:
        def html(self, path):
            seen.append(path)
            if path.endswith("/problems"):
                raise RobotsDisallowed("route disallowed")
            return (
                '<div class="problem-statement"><div>Allowed statement</div></div>',
                {},
            )

    Crawler(s, Client()).statements(4, ["4A", "4B"])
    assert seen == [
        "/contest/4/problems",
        "/problemset/problem/4/A",
        "/problemset/problem/4/B",
    ]
    assert s.problem("4B")["statement_status"] == "complete"


def test_isolated_failure_retries_only_failed_item(seeded):
    s, *_ = seeded
    m = JobManager(s)
    seen = []

    def collect(pid):
        seen.append(pid)
        if pid == "4A":
            raise ValueError("malformed problem")
        s.save_statement(pid, {"description": pid})

    try:
        m.crawler.statement = collect
        j = m.create("statements", {})
        m.futures[j["id"]].result(timeout=5)
        assert m.get(j["id"])["state"] == "completed_with_errors"
        assert m.get(j["id"])["succeeded"] == 1
        assert m.get(j["id"])["failed"] == 1

        def fixed(pid):
            seen.append(pid)
            s.save_statement(pid, {"description": pid})

        m.crawler.statement = fixed
        m.resume(j["id"])
        m.futures[j["id"]].result(timeout=5)
        assert seen == ["4A", "4B", "4A"]
        assert m.get(j["id"])["state"] == "completed"
        assert [i["attempts"] for i in m.items(j["id"])] == [2, 1]
    finally:
        m.close()


def test_second_collector_cannot_reset_first_job(seeded):
    from cpbench.locking import CollectorBusy

    s, *_ = seeded
    m = JobManager(s)
    try:
        with s.connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES('owned','statements','running','{}',1,0,NULL,'a','a')"
            )
        with pytest.raises(CollectorBusy):
            JobManager(s)
        assert m.get("owned")["state"] == "running"
    finally:
        m.close()
    # Lock must be released after shutdown.
    other = JobManager(s)
    other.close()


def test_network_outage_stops_repeated_target_failures(seeded):
    import httpx

    s, *_ = seeded
    m = JobManager(s)
    seen = []

    def outage(pid):
        seen.append(pid)
        raise httpx.ConnectError("DNS unavailable")

    try:
        m.crawler.statement = outage
        j = m.create("statements", {})
        m.futures[j["id"]].result(timeout=5)
        assert m.get(j["id"])["state"] == "failed"
        assert seen == ["4A"]
        assert m.get(j["id"])["outcomes"] == {"failed": 1, "pending": 1}
    finally:
        m.close()


def test_pause_interrupts_retry_wait(seeded):
    from cpbench.crawler import CollectionPaused

    s, *_ = seeded
    client = CFClient(s)
    try:
        client.cancel_check = lambda: False
        with pytest.raises(CollectionPaused):
            client._sleep(120)
    finally:
        client.client.close()


@pytest.mark.parametrize("invalid", ["missing", "corrupt", "api_failed"])
def test_invalid_cache_is_refetched(seeded, invalid):
    import httpx

    s, *_ = seeded
    url = "https://codeforces.com/api/contest.list"
    payload = (
        b'{"status":"FAILED","comment":"limit"}'
        if invalid == "api_failed"
        else b'{"status":"OK","result":[]}'
    )
    prov = s.evidence(url, payload)
    path = s.root / "raw" / prov["sha256"]
    if invalid == "missing":
        path.unlink()
    elif invalid == "corrupt":
        path.write_bytes(b"corrupt")
    client = CFClient(s)
    client.client.close()
    seen = []

    def fetch(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "OK", "result": [1]})

    client.client = httpx.Client(transport=httpx.MockTransport(fetch))
    try:
        assert client.api("contest.list")[0]["result"] == [1]
        assert seen == [url]
    finally:
        client.client.close()


def test_transport_retry_then_success(seeded):
    import httpx

    s, *_ = seeded
    client = CFClient(s)
    client.client.close()
    seen = []

    def fetch(request):
        seen.append(1)
        if len(seen) < 3:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"status": "OK", "result": []})

    client.client = httpx.Client(transport=httpx.MockTransport(fetch))
    client._sleep = lambda seconds: None
    try:
        assert client.api("contest.list", cached=False)[0]["status"] == "OK"
        assert len(seen) == 3
    finally:
        client.client.close()


def test_source_restriction_does_not_stop_other_targets(seeded):
    s, *_ = seeded

    class Client:
        def api(self, *args):
            return {
                "result": [
                    dict(
                        id=i,
                        problem={"contestId": 4, "index": index},
                        verdict="OK",
                        programmingLanguage="GNU C++17",
                    )
                    for i, index in [(101, "A"), (102, "B")]
                ]
            }, {}

        def html(self, path):
            raise BlockedError("restricted")

    outcomes = []
    Crawler(s, Client()).references(
        4, ["4A", "4B"], on_item=lambda *x: outcomes.append(x)
    )
    assert len(outcomes) == 2 and all(x[1] == "partial" for x in outcomes)
    assert s.stats()["reference_metadata"] == 2 and s.stats()["references"] == 0


def test_declared_alias_and_duplicate_groups_are_transitive(seeded):
    from cpbench.export import assign_splits

    rows = [
        {
            "id": "4A",
            "contest_id": 4,
            "statement": {"description": "one", "aliases": ["8/B"]},
        },
        {"id": "8B", "contest_id": 8, "statement": {"description": "two   words"}},
        {"id": "9A", "contest_id": 9, "statement": {"description": "two\nwords"}},
        {"id": "9B", "contest_id": 9, "statement": None},
    ]
    result = assign_splits(rows)
    assert {r["split_group"] for r in result} == {"4"}
    assert {r["split"] for r in result} == {split_for(4)}
    # Result does not depend on input order.
    assert {r["split_group"] for r in assign_splits(list(reversed(rows)))} == {"4"}


def test_filtered_exports_preserve_groups(seeded):
    s, *_ = seeded
    s.save_statement("4B", {"description": "alias", "aliases": ["1/A"]})
    full = {r["id"]: r for r in records(s)}
    filtered = list(records(s, {"min_rating": 800}))
    assert filtered[0]["split_group"] == full["4A"]["split_group"] == "1"
    assert list(records(s, {"status": "available"}))[0]["id"] == "4B"


def test_freeze_manifest_counts_same_snapshot_and_immutable_file(seeded, tmp_path):
    import json

    s, *_ = seeded
    s.stats = lambda: pytest.fail("Do not use a later DB snapshot for counts")
    manifest = freeze(s, tmp_path / "frozen")
    path = tmp_path / "frozen" / manifest["file"]
    body = path.read_bytes()
    assert digest(body) == manifest["sha256"]
    rows = [json.loads(line) for line in body.splitlines()]
    assert len(rows) == manifest["records"] == manifest["coverage"]["total"] == 2
    assert sum(manifest["split"]["actual_counts"].values()) == 2
    s.save_statement("4A", {"description": "new"})
    next_manifest = freeze(s, tmp_path / "frozen")
    assert next_manifest["file"] != manifest["file"]
    assert path.read_bytes() == body


def test_direct_verification_preserves_imported_evidence(seeded):
    s, *_ = seeded
    imported = {
        "description": "old",
        "editorial": "SECRET",
        "aliases": ["1/A"],
        "provenance": {"revision": "old"},
    }
    s.save_statement("4A", imported, "imported")
    s.save_statement("4A", {"description": "primary"})
    s.save_statement("4A", {"description": "updated primary"})
    record = s.problem("4A")
    assert record["statement"]["imported_reference"] == imported
    assert "SECRET" not in canonical(list(records(s, prompts_only=True)))
    assert list(records(s))[0]["split_group"] == "1"


def test_reference_metadata_only_never_requests_source(seeded):
    s, *_ = seeded

    class Client:
        def api(self, *args):
            return {
                "result": [
                    dict(
                        id=202,
                        problem={"contestId": 4, "index": "A"},
                        verdict="OK",
                        programmingLanguage="GNU C++17",
                    )
                ]
            }, {}

        def html(self, path):
            pytest.fail("metadata_only must not request source pages")

    outcome = []
    Crawler(s, Client()).references(
        4, ["4A"], metadata_only=True, on_item=lambda *x: outcome.append(x)
    )
    assert outcome == [("4A", "done", None)]
    assert s.problem("4A")["reference_status"] == "metadata_only"


def test_evidence_repairs_corrupt_blob(seeded):
    s, *_ = seeded
    body = b"original bytes"
    prov = s.evidence("https://codeforces.com/test", body)
    path = s.root / "raw" / prov["sha256"]
    path.write_bytes(b"broken")
    s.evidence("https://codeforces.com/test", body)
    assert path.read_bytes() == body


def test_api_checkpoint_outcomes_and_available_filter(seeded):
    s, *_ = seeded
    s.save_statement("4A", {"description": "imported"}, "imported")
    app = create_app(s.root)
    with TestClient(app) as client:
        assert client.get("/api/problems?status=available").json()["total"] == 1
        app.state.manager.crawler.statement = lambda pid: s.save_statement(
            pid, {"description": "direct"}
        )
        response = client.post("/api/jobs", json={"kind": "statements", "limit": 1})
        assert response.status_code == 202
        jid = response.json()["id"]
        app.state.manager.futures[jid].result(timeout=5)
        rows = client.get(f"/api/jobs/{jid}/items").json()
        assert rows[0]["item_id"] == "4B" and rows[0]["state"] == "done"
        assert client.get("/api/jobs").json()[0]["succeeded"] == 1
        assert client.get("/api/jobs/unknown/items").status_code == 404
