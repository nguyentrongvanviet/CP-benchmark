"""Fail-closed Docker runner. Candidate code never executes on the API host."""

import json
import os
import subprocess
import uuid
from pathlib import Path
from .store import canonical, digest

IMAGE = os.environ.get("CPBENCH_JUDGE_IMAGE", "cpbench-judge:v1")


def environment():
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode:
            return {
                "available": False,
                "error": "Start Docker and run: docker build -t cpbench-judge:v1 judge",
            }
        return {
            "available": True,
            "image": IMAGE,
            "image_id": result.stdout.strip(),
            "profile": "GNU C++20 / Linux / -O2",
            "codeforces_equivalent": False,
        }
    except (OSError, subprocess.TimeoutExpired):
        return {
            "available": False,
            "error": "Docker is unavailable. No host execution fallback.",
        }


def evaluate(source, tests, manifest, image_id=None):
    info = environment()
    if not info["available"]:
        return {"verdict": "INFRA_ERROR", "error": info["error"]}
    pinned = image_id or info["image_id"]
    name = "cpbench-" + uuid.uuid4().hex
    payload = dict(
        source_code=source,
        tests=tests,
        time_limit_ms=manifest["time_limit_ms"],
        memory_limit_mb=manifest["memory_limit_mb"],
        checker=manifest.get("checker", "exact_tokens_v1"),
    )
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cpus=1",
        "--memory=1024m",
        "--memory-swap=1024m",
        "--pids-limit=64",
        "--cap-drop=ALL",
        "--cap-add=SETUID",
        "--cap-add=SETGID",
        "--cap-add=KILL",
        "--cap-add=CHOWN",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        "/work:rw,exec,nosuid,size=128m,mode=755",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        pinned,
    ]
    timeout = min(900, 80 + len(tests) * (manifest["time_limit_ms"] / 1000 * 2 + 1))
    try:
        process = subprocess.run(
            command,
            input=canonical(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if process.returncode:
            return {
                "verdict": "INFRA_ERROR",
                "error": process.stderr[:4000]
                or f"Container exited {process.returncode}",
            }
        result = json.loads(process.stdout)
        result["source_sha256"] = digest(source.encode())
        result.setdefault("environment", {}).update(
            image_id=pinned, runner_sha256=digest(Path(__file__).read_bytes())
        )
        return result
    except subprocess.TimeoutExpired:
        return {
            "verdict": "INFRA_ERROR",
            "error": "Container supervisor exceeded deadline",
        }
    except (OSError, ValueError) as exc:
        return {"verdict": "INFRA_ERROR", "error": str(exc)[:1000]}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
