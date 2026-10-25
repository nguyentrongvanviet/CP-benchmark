import hashlib
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from cpbench.generators import generate, validate, brute, oracle
from cpbench.lab import Lab, summarize, source_code
from cpbench.store import Store, canonical, digest
from cpbench.account import signed_params, import_rows
from cpbench.api import create_app


@pytest.mark.parametrize("pid", ["4A", "1A", "158A", "189A", "455A", "474B"])
def test_generators_deterministic_validated_and_independent(pid):
    cases = generate(pid, 42, 12)
    assert cases == generate(pid, 42, 12)
    assert len(canonical(cases)) < 8 * 1024**2
    checked = 0
    for case in cases:
        validate(pid, case["input"])
        b = brute(pid, case["input"])
        if b is not None:
            checked += 1
            assert b.split() == case["output"].split()
    assert checked >= 10


@pytest.mark.parametrize(
    "pid,bad",
    [
        ("4A", "0"),
        ("1A", "1 2 0"),
        ("158A", "3 2\n1 2 0"),
        ("189A", "7 4 4 4"),
        ("455A", "2\n1"),
        ("474B", "1\n2\n1\n3"),
    ],
)
def test_invalid_inputs_rejected(pid, bad):
    with pytest.raises((AssertionError, ValueError)):
        validate(pid, bad)


def test_pass_at_k_is_per_problem_and_does_not_hide_missing():
    rows = [
        dict(problem_id="a", verdict=v, rating=800, tags=["math"])
        for v in ["AC", "WA", "WA"]
    ] + [
        dict(problem_id="b", verdict="AC", rating=1200, tags=["dp"]),
        dict(problem_id="c", verdict="INFRA_ERROR", rating=1600, tags=["dp"]),
    ]
    r = summarize(rows, ["a", "b", "c", "d"])
    assert r["pass_at_1"] == pytest.approx(2 / 3)
    assert r["coverage"] == 0.5
    assert r["infrastructure_errors"] == 1
    assert r["missing_problem_ids"] == ["c", "d"]
    assert r["pass_at_k"]["2"]["value"] == pytest.approx(2 / 3)
    assert r["pass_at_k"]["2"]["eligible_problems"] == 1
    assert r["by_rating"]["1600"]["pass_at_1"] is None
    assert r["by_rating"]["1600"]["infrastructure_errors"] == 1
    assert r["by_tags"]["dp"]["pass_at_1"] == 1
    assert "wilson95" not in r


def test_source_extraction_no_ambiguous_multiple_blocks():
    assert source_code("Explanation\n```cpp\nint main(){}\n```") == "int main(){}\n"
    with pytest.raises(ValueError):
        source_code("```cpp\nx\n```\n```cpp\ny\n```")


def test_signature_uses_sorted_unencoded_fields():
    got = signed_params(
        "user.status",
        {"handle": "Viet_love_KA", "includeSources": "true"},
        "key",
        "secret",
        123,
        "123456",
    )
    message = "123456/user.status?apiKey=key&handle=Viet_love_KA&includeSources=true&time=123#secret"
    assert got["apiSig"] == "123456" + hashlib.sha512(message.encode()).hexdigest()
    assert "secret" not in canonical(got)


def freeze_fixture(lab, pid="4A"):
    pack = {
        "manifest": {
            "id": pid,
            "rating": 800,
            "tags": ["math"],
            "time_limit_ms": 1000,
            "memory_limit_mb": 128,
        },
        "tests": [{"input": "4", "output": "YES"}],
        "validation": {
            "passed": True,
            "package_sha256": lab.fingerprint(pid),
            "environment": {"image_id": "sha256:test"},
        },
    }
    raw = canonical(pack).encode()
    version = digest(raw)
    (lab.frozen / (version + ".json")).write_bytes(raw)
    with lab.store.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO lab_packages VALUES(?,?,?)",
            (pid, version, canonical({"passed": True})),
        )
    return version


def test_hash_integrity_and_problem_binding(tmp_path):
    lab = Lab(Store(tmp_path))
    try:
        version = freeze_fixture(lab)
        assert lab.load_testset("4A", version)[0] == version
        with pytest.raises(ValueError):
            lab.load_testset("1A", version)
        (lab.frozen / (version + ".json")).write_text("{}")
        with pytest.raises(ValueError):
            lab.load_testset("4A", version)
    finally:
        lab.close()


def test_submit_url_idempotency_and_jsonl_rejects_duplicates(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path)) as client:
        lab = client.app.state.lab
        version = freeze_fixture(lab)
        monkeypatch.setattr(lab, "work", lambda *args: None)
        payload = {
            "problem_id": "https://codeforces.com/problemset/problem/4/A",
            "source_code": "int main(){}",
            "idempotency_key": "key",
        }
        a = client.post("/api/submissions", json=payload)
        assert a.status_code == 202
        assert (
            client.post("/api/submissions", json=payload).json()["id"] == a.json()["id"]
        )
        payload["source_code"] = "different"
        assert client.post("/api/submissions", json=payload).status_code == 422
        duplicate = "\n".join(
            [json.dumps({"problem_id": "4A", "source_code": "int main(){}"})] * 2
        )
        assert (
            client.post(
                "/api/benchmark/runs", json={"problem_ids": ["4A"], "jsonl": duplicate}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/submissions", json={"problem_id": "999X", "source_code": "x"}
            ).status_code
            == 422
        )
        assert (
            client.post("/api/testsets", json={"problem_id": "../../evil"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/submissions",
                content="x" * (5 * 1024**2 + 1),
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )


def test_browser_copy_normalization_preserves_program():
    from cpbench.account import normalize_browser_source

    original = 'int main(){\n\u00a0\nconst char*s="a\u00a0b";\n}'
    assert (
        normalize_browser_source(original)
        == 'int main(){\n\nconst char*s="a\u00a0b";\n}'
    )
