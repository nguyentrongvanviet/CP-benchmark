"""Optional Codeforces own-account API import. Secrets are memory-only and never logged."""

import hashlib
import json
import secrets
import time
from urllib.parse import urlencode
import httpx
from .store import canonical, digest, now


def signed_params(method, params, key, secret, timestamp=None, nonce=None):
    params = {k: str(v) for k, v in params.items()}
    params.update(apiKey=key, time=str(timestamp or int(time.time())))
    nonce = nonce or secrets.token_hex(3)
    message = (
        nonce
        + "/"
        + method
        + "?"
        + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        + "#"
        + secret
    )
    params["apiSig"] = nonce + hashlib.sha512(message.encode()).hexdigest()
    return params


def import_rows(store, rows, provenance, source_origin="codeforces_authenticated_api"):
    saved = sources = 0
    for row in rows:
        if row.get("verdict") != "OK" or not any(
            s in row.get("programmingLanguage", "") for s in ("C++", "Clang++")
        ):
            continue
        p = row["problem"]
        pid = f"{p.get('contestId', row.get('contestId'))}{p['index']}"
        if not store.problem(pid, include_source=False):
            continue
        code = row.get("source") or row.get("sourceCode")
        if not isinstance(code, str) or not code.strip():
            code = None
        if code and len(code.encode()) > 256000:
            continue
        record = {k: v for k, v in row.items() if k not in ("source", "sourceCode")}
        record.update(
            url=f"https://codeforces.com/contest/{row['contestId']}/submission/{row['id']}",
            provenance=provenance,
            source_origin=source_origin if code else None,
            local_validation="not_run",
        )
        with store.connect() as db:
            previous = db.execute(
                "SELECT record,source FROM reference_solutions WHERE submission_id=?",
                (row["id"],),
            ).fetchone()
            if previous and previous["source"] and not code:
                old = json.loads(previous["record"])
                for field in (
                    "source_origin",
                    "source_provenance",
                    "source_binding",
                    "source_normalization",
                    "local_validation",
                ):
                    if field in old:
                        record[field] = old[field]
            db.execute(
                """INSERT INTO reference_solutions VALUES(?,?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET
                        record=excluded.record,source=COALESCE(excluded.source,reference_solutions.source),source_sha256=COALESCE(excluded.source_sha256,reference_solutions.source_sha256)""",
                (
                    row["id"],
                    pid,
                    canonical(record),
                    code,
                    digest(code.encode()) if code else None,
                ),
            )
            db.execute(
                "UPDATE problems SET reference_status=CASE WHEN EXISTS(SELECT 1 FROM reference_solutions WHERE problem_id=? AND source IS NOT NULL) THEN 'complete' ELSE 'metadata_only' END WHERE id=?",
                (pid, pid),
            )
        saved += 1
        sources += bool(code)
    return {
        "accepted_cpp_metadata": saved,
        "source_bodies": sources,
        "scanned": len(rows),
    }


def import_account(store, client, handle, key="", secret="", count=100, offset=1):
    params = {"handle": handle, "from": offset, "count": count}
    if bool(key) != bool(secret):
        raise ValueError("Provide both API key and secret, or neither")
    authenticated = bool(key and secret)
    if authenticated:
        params["includeSources"] = "true"
    # Share collector's pacing lock. Never feed authenticated URLs into raw fetch logs.
    with client.lock:
        time.sleep(max(0, client.interval - (time.monotonic() - client.last)))
        client.last = time.monotonic()
        if authenticated:
            params = signed_params("user.status", params, key, secret)
        try:
            r = client.client.get(
                "https://codeforces.com/api/user.status", params=params
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            raise ValueError(
                "Codeforces request failed; check connection/API credentials. Sensitive URL omitted."
            ) from None
    if data.get("status") != "OK":
        raise ValueError(
            "Codeforces denied user.status. Verify handle, API key owner, permissions and system clock."
        )
    rows = data["result"]
    # Source response evidence contains data, never API key/signature.
    public_url = "https://codeforces.com/api/user.status?" + urlencode(
        {"handle": handle, "from": offset, "count": count}
    )
    prov = store.evidence(public_url, canonical(data).encode())
    prov["authenticated"] = authenticated
    result = import_rows(store, rows, prov)
    result.update(
        handle=handle,
        authenticated=authenticated,
        next_offset=offset + len(rows),
        note="Source is available only for your own account with an authorized API key."
        if not result["source_bodies"]
        else "Source imported; local validation still required.",
    )
    return result


def normalize_browser_source(text):
    """Prettify represents empty lines as NBSP; preserve all nonempty source lines."""
    return "\n".join(
        "" if "\u00a0" in line and not line.strip() else line
        for line in text.split("\n")
    )
