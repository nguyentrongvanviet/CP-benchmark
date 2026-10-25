"""Container-only supervisor. Candidate processes cannot read the root-only payload.

One container per submission; one fresh working directory per test. No host runner.
"""

import json
import ctypes
import math
import os
import platform
import re
import resource
import selectors
import shutil
import signal
import subprocess
import time
import sys
from pathlib import Path

FLAGS = ["-std=c++20", "-O2", "-pipe", "-DONLINE_JUDGE"]
MAX_OUTPUT = 1024 * 1024


def candidate_seccomp():
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(
        0x7FFF0000
    )  # SCMP_ACT_ALLOW; Docker default filter is also active.
    if not context:
        raise RuntimeError("Cannot initialize candidate seccomp")
    try:
        for name in (
            "clone",
            "clone3",
            "fork",
            "vfork",
            "socket",
            "socketpair",
            "ptrace",
            "process_vm_readv",
            "process_vm_writev",
            "mount",
            "unshare",
            "setns",
            "bpf",
        ):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if (
                number >= 0
                and lib.seccomp_rule_add(context, 0x80000000, number, 0) != 0
            ):
                raise RuntimeError("Cannot install syscall rule")
        if lib.seccomp_load(context) != 0:
            raise RuntimeError("Cannot load candidate seccomp")
    finally:
        lib.seccomp_release(context)


def child_limits(cpu_seconds, address_bytes, compile_step):
    os.setsid()
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    resource.setrlimit(
        resource.RLIMIT_CPU, (math.ceil(cpu_seconds), math.ceil(cpu_seconds) + 1)
    )
    resource.setrlimit(resource.RLIMIT_AS, (address_bytes, address_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if not compile_step:
        candidate_seccomp()


def run(command, stdin, cwd, seconds, memory_mb, compile_step=False):
    start = time.monotonic()
    # Read-only file descriptor is inherited; the payload path remains inaccessible.
    infile = Path("/work/.stdin")
    infile.write_bytes(stdin.encode())
    infile.chmod(0o600)
    out = bytearray()
    err = bytearray()
    cap = MAX_OUTPUT
    reason = None
    usage = None
    peak = 0
    with infile.open("rb") as stream:
        proc = subprocess.Popen(
            command,
            stdin=stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": cwd},
            preexec_fn=lambda: child_limits(
                seconds, memory_mb * 1024**2 * 2, compile_step
            ),
        )
    sel = selectors.DefaultSelector()
    for pipe, target in [(proc.stdout, out), (proc.stderr, err)]:
        os.set_blocking(pipe.fileno(), False)
        sel.register(pipe, selectors.EVENT_READ, target)
    status = None
    while status is None or sel.get_map():
        elapsed = time.monotonic() - start
        try:
            content = Path(f"/proc/{proc.pid}/status").read_text()
            rss = int(
                next(
                    (
                        s.split()[1]
                        for s in content.splitlines()
                        if s.startswith("VmRSS:")
                    ),
                    0,
                )
            )
            peak = max(peak, rss)
            if rss > memory_mb * 1024:
                reason = reason or "MLE"
        except (FileNotFoundError, ProcessLookupError):
            pass
        if elapsed > seconds * 2 + 0.5:
            reason = reason or "TLE"
        if reason:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for key, _ in sel.select(0.005):
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                sel.unregister(key.fileobj)
                key.fileobj.close()
            else:
                target = key.data
                target.extend(chunk[: max(0, cap - len(target))])
                if len(target) >= cap:
                    reason = reason or "OLE"
        if status is None:
            pid, code, ru = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                status, usage = code, ru
                proc.returncode = os.waitstatus_to_exitcode(code)
                # Descendant processes must not retain pipes or survive the test.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    sel.close()
    cpu = (usage.ru_utime + usage.ru_stime) * 1000
    peak = max(peak, usage.ru_maxrss)
    if peak > memory_mb * 1024:
        reason = reason or "MLE"
    if reason is None:
        if cpu > seconds * 1000 or proc.returncode == -signal.SIGXCPU:
            reason = "TLE"
        elif proc.returncode == -signal.SIGSYS:
            reason = "SECURITY_VIOLATION"
        elif proc.returncode != 0:
            reason = "RTE"
        else:
            reason = "OK"
    return {
        "verdict": reason,
        "exit_code": proc.returncode,
        "signal": -proc.returncode if proc.returncode < 0 else None,
        "cpu_ms": round(cpu, 3),
        "wall_ms": round((time.monotonic() - start) * 1000, 3),
        "memory_kb": peak,
        "stdout": out.decode(errors="replace"),
        "stderr": err.decode(errors="replace"),
    }


def main():
    payload = json.load(sys.stdin)
    Path("/work/build").mkdir()
    Path("/work/build").chmod(0o777)
    Path("/work/build/main.cpp").write_text(payload["source_code"])
    compiled = run(
        ["g++", *FLAGS, "main.cpp", "-o", "main"], "", "/work/build", 30, 768, True
    )
    metadata = {
        "compiler": subprocess.check_output(
            ["g++", "--version"], text=True
        ).splitlines()[0],
        "flags": FLAGS,
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "isolation": "Docker Linux; no network; non-root candidate; seccomp default + candidate process/network deny; per-case rlimits",
    }
    result = {
        "environment": metadata,
        "compile": compiled,
        "tests": [],
        "verdict": "CE",
    }
    if compiled["verdict"] != "OK":
        result["compile"]["stdout"] = compiled["stdout"][:16000]
        result["compile"]["stderr"] = compiled["stderr"][:16000]
        return result
    shutil.move("/work/build/main", "/work/main")
    os.chown("/work/main", 0, 0)
    os.chmod("/work/main", 0o555)
    shutil.rmtree("/work/build")
    result["verdict"] = "AC"
    for index, case in enumerate(payload["tests"]):
        Path("/work/run").mkdir(mode=0o777)
        os.chmod("/work/run", 0o777)
        run_result = run(
            ["/work/main"],
            case["input"],
            "/work/run",
            payload["time_limit_ms"] / 1000,
            payload["memory_limit_mb"],
        )
        if run_result["verdict"] == "OK":
            actual, expected = run_result["stdout"].split(), case["output"].split()
            checker = payload.get("checker", "exact_tokens_v1")
            if checker == "integer_tokens_v1":
                try:
                    accepted = len(actual) == len(expected) and all(
                        re.fullmatch(r"[+-]?[0-9]+", a) and int(a) == int(b)
                        for a, b in zip(actual, expected)
                    )
                except ValueError:
                    accepted = False
            elif checker == "yesno_casefold_v1":
                accepted = [a.lower() for a in actual] == [b.lower() for b in expected]
            else:
                accepted = actual == expected
            run_result["verdict"] = "AC" if accepted else "WA"
        run_result.update(
            index=index + 1,
            category=case.get("category", "custom"),
            checker=payload.get("checker", "exact_tokens_v1"),
            stdout=run_result["stdout"][:4000],
            stderr=run_result["stderr"][:4000],
        )
        result["tests"].append(run_result)
        shutil.rmtree("/work/run")
        if run_result["verdict"] != "AC":
            result["verdict"] = run_result["verdict"]
            break
    result["passed"] = sum(t["verdict"] == "AC" for t in result["tests"])
    result["total"] = len(payload["tests"])
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as exc:
        print(
            json.dumps(
                {"verdict": "INFRA_ERROR", "error": f"{type(exc).__name__}: {exc}"}
            )
        )
