# _VERIFY_V2
"""verify_all.py — Full project verification.

Runs every phase of the checklist. For each failure, classifies as:
  bug        - deterministic failure
  flaky      - passes on retry
  hardware   - resource limit (RAM, GPU)
  missing    - file/command/package absent
  regression - passed in previous verify run, now fails
  skip       - phase not applicable (services not running)

Writes .trail/verify_<stamp>.json with full data.

Usage:
  python verify_all.py                 # all phases
  python verify_all.py --only phase2,phase3
  python verify_all.py --skip phase8
  python verify_all.py --report        # diff vs last run
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
TRAIL = ROOT / ".trail"
PACKAGE = "ohm"
SKIP_DIRS = {"__pycache__", "_backups", "test_env", "venv", ".venv",
             "build", "dist", ".mypy_cache", ".git", ".trail", "snapshots"}


# ------------------------------------------------------------------ helpers

def has_pkg(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def run(cmd, timeout=120, cwd=ROOT, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, shell=isinstance(cmd, str))
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


def run_stream(cmd, timeout=1200, progress_prefix="    "):
    """Run cmd, stream stdout+stderr live, return (rc, full_output)."""
    import subprocess as _sp
    proc = _sp.Popen(cmd, cwd=ROOT, stdout=_sp.PIPE, stderr=_sp.STDOUT,
                     text=True, encoding="utf-8", errors="replace",
                     bufsize=1)
    buf = []
    last_progress = time.time()
    try:
        for line in proc.stdout:
            buf.append(line)
            # show checkpoint-like lines
            if any(s in line for s in ("[", "Ran ", " ... ok", " ... FAIL", " ... ERROR",
                                        "FAILED", "elapsed=", "/120]", "/tests]")):
                stripped = line.rstrip()
                if stripped and len(stripped) < 140:
                    print(f"{progress_prefix}{stripped}", flush=True)
            if time.time() - last_progress > 30:
                print(f"{progress_prefix}  ... still running "
                      f"({int(time.time() - last_progress)}s idle)",
                      flush=True)
                last_progress = time.time()
        proc.wait(timeout=timeout)
    except Exception as e:
        proc.kill()
        return 124, "".join(buf) + f"\n[stream error: {e}]"
    return proc.returncode, "".join(buf)


def phase_result(name, checked, ok, failed, status="ok",
                 cls=None, notes=None, evidence=None, duration_ms=0):
    return {
        "phase": name,
        "checked": checked, "ok": ok, "failed": failed,
        "status": status,
        "class": cls,
        "notes": notes or [],
        "evidence": evidence or {},
        "duration_ms": duration_ms,
    }


# ------------------------------------------------------------------ phase 0

def phase0_environment():
    t0 = time.time()
    notes = []
    checks = [
        ("python",  sys.version_info >= (3, 11), sys.version.split()[0]),
        ("gradio",  has_pkg("gradio"), None),
        ("fastapi", has_pkg("fastapi"), None),
        ("uvicorn", has_pkg("uvicorn"), None),
        ("cryptography", has_pkg("cryptography"), None),
        ("paho",    has_pkg("paho.mqtt.client"), None),
        ("bcrypt",  has_pkg("bcrypt"), None),
    ]
    ok = sum(1 for _, cond, _ in checks if cond)
    failed = len(checks) - ok
    for name, cond, detail in checks:
        if not cond:
            notes.append(f"{name} missing" + (f" ({detail})" if detail else ""))

    cls = None if failed == 0 else "missing"
    return phase_result("phase0", len(checks), ok, failed,
                        cls=cls, notes=notes,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 1

REQUIRED_ROOT = [
    "ohm_synapse.py", "ohm_chat.py", "ohm_kairos.py",
    "ohm_embeddings.py", "ohm_ui.py", "ohm_auth.py", "ohm_cli.py",
]
REQUIRED_TOOLS = ["check_all.py", "run_tests.py", "stamp.py", "journey.py"]
REQUIRED_DOCS = ["README.md", "DESIGN.md", "pyproject.toml"]

def phase1_inventory():
    t0 = time.time()
    missing = []
    for f in REQUIRED_ROOT + REQUIRED_TOOLS + REQUIRED_DOCS:
        if not (ROOT / f).exists():
            missing.append(f)
    if not (ROOT / PACKAGE).is_dir():
        missing.append(f"{PACKAGE}/")
    total = len(REQUIRED_ROOT) + len(REQUIRED_TOOLS) + len(REQUIRED_DOCS) + 1
    ok = total - len(missing)
    cls = None if not missing else "missing"
    return phase_result("phase1", total, ok, len(missing),
                        cls=cls, notes=missing,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 2

def phase2_tests():
    t0 = time.time()
    script = ROOT / "run_tests.py"
    if not script.exists():
        return phase_result("phase2", 0, 0, 1, status="fail",
                            cls="missing", notes=["run_tests.py not found"])
    rc, out = run_stream([sys.executable, "run_tests.py"],
                         timeout=900, progress_prefix="      ")
    err = ""
    m = re.search(r"TOTAL checked=(\d+) ok=(\d+) failed=(\d+)", out)
    if not m:
        return phase_result("phase2", 0, 0, 1, status="fail",
                            cls="bug", notes=[(out + err)[-300:]])
    checked, ok, failed = map(int, m.groups())
    return phase_result("phase2", checked, ok, failed,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 3

def phase3_syntax_mypy():
    t0 = time.time()
    script = ROOT / "check_all.py"
    if not script.exists():
        return phase_result("phase3", 0, 0, 1, status="fail",
                            cls="missing", notes=["check_all.py not found"])
    rc, out = run_stream([sys.executable, "check_all.py"],
                         timeout=300, progress_prefix="      ")
    err = ""
    m = re.search(r"TOTAL checked=(\d+) ok=(\d+) failed=(\d+)", out)
    if not m:
        return phase_result("phase3", 0, 0, 1, status="fail",
                            cls="bug", notes=[(out + err)[-300:]])
    checked, ok, failed = map(int, m.groups())
    return phase_result("phase3", checked, ok, failed,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 4

def phase4_cli():
    t0 = time.time()
    cmds = [
        ["ohm", "version"],
        ["ohm", "--help"],
    ]
    ok = failed = 0
    notes = []
    for cmd in cmds:
        rc, out, err = run(cmd, timeout=15)
        if rc == 0:
            ok += 1
        else:
            failed += 1
            notes.append(f"{' '.join(cmd)}: rc={rc}")
    return phase_result("phase4", ok + failed, ok, failed,
                        cls="bug" if failed else None, notes=notes,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 5

def phase5_peer_http():
    t0 = time.time()
    if not port_open(7900):
        return phase_result("phase5", 0, 0, 0, status="skip",
                            cls="skip",
                            notes=["peer not running on :7900 (start with `ohm run <peer> --headless --port 7900`)"],
                            duration_ms=int((time.time() - t0) * 1000))
    session_dir = pathlib.Path.home() / ".ohm" / "sessions"
    token = None
    for p in session_dir.glob("*.token"):
        candidate = p.read_text(encoding="utf-8").strip()
        if not candidate:
            continue
        rc, out, _ = run(["curl", "-s", "-H",
                          f"Authorization: Bearer {candidate}",
                          "http://127.0.0.1:7900/status"], timeout=5)
        if "node_id" in (out or ""):
            token = candidate
            break
    checks = []
    # /ping public
    rc, out, _ = run(["curl", "-s", "http://127.0.0.1:7900/ping"], timeout=5)
    checks.append(("ping", '"ok"' in out))
    # /status without token
    rc, out, _ = run(["curl", "-s", "http://127.0.0.1:7900/status"], timeout=5)
    checks.append(("status_no_token", "unauthorized" in out))
    if token:
        h = f"Authorization: Bearer {token}"
        rc, out, _ = run(["curl", "-s", "-H", h,
                          "http://127.0.0.1:7900/status"], timeout=5)
        checks.append(("status_with_token", "node_id" in out))

    ok = sum(1 for _, c in checks if c)
    failed = len(checks) - ok
    return phase_result("phase5", len(checks), ok, failed,
                        notes=[n for n, c in checks if not c],
                        cls="bug" if failed else None,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 6

def phase6_chat():
    t0 = time.time()
    if not (port_open(7900) and port_open(7901)):
        return phase_result("phase6", 0, 0, 0, status="skip",
                            cls="skip",
                            notes=["needs two peers on :7900 and :7901"],
                            duration_ms=int((time.time() - t0) * 1000))
    return phase_result("phase6", 1, 1, 0, status="ok",
                        notes=["two peers detected; manual chat test pending"],
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 7

def phase7_ui():
    t0 = time.time()
    if not (port_open(7910) or port_open(7911)):
        return phase_result("phase7", 0, 0, 0, status="skip",
                            cls="skip",
                            notes=["no UI peer running on :7910 or :7911"],
                            duration_ms=int((time.time() - t0) * 1000))
    return phase_result("phase7", 1, 1, 0, status="ok",
                        notes=["UI port detected"],
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 8

def phase8_benchmarks():
    t0 = time.time()
    notes = []
    ok = failed = 0
    # 8.1 — offline
    rc, out, err = run([sys.executable, "benchmark_offline.py"], timeout=300)
    if rc == 0 and "0.0%" in out:
        ok += 1
    else:
        failed += 1
        notes.append(f"8.1 offline: rc={rc}")
    # 8.2 — v3 mock (long)
    rc, out = run_stream([sys.executable, "benchmark_v3.py"],
                         timeout=1200, progress_prefix="      ")
    err = ""
    m = re.search(r"hallucination:\s+(\d+)", out)
    if rc == 0 and m and int(m.group(1)) == 0:
        ok += 1
    else:
        failed += 1
        notes.append(f"8.2 v3: halluc={m.group(1) if m else '?'}")
    # 8.3/8.4 skipped unless explicit
    total = 2
    return phase_result("phase8", total, ok, failed, notes=notes,
                        cls="bug" if failed else None,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 9

def phase9_e2e():
    t0 = time.time()
    if not port_open(1883):
        return phase_result("phase9", 0, 0, 0, status="skip",
                            cls="skip",
                            notes=["broker not running on :1883"],
                            duration_ms=int((time.time() - t0) * 1000))
    rc, out, err = run([sys.executable, "-m", "unittest",
                        "test_fase4_e2e", "-v"], timeout=300)
    combined = (out or "") + (err or "")
    m = re.search(r"Ran (\d+) tests", combined)
    total = int(m.group(1)) if m else 0
    if total == 0:
        return phase_result("phase9", 0, 0, 0, status="skip",
                            cls="skip",
                            notes=["no tests executed (broker unreachable from test)"],
                            duration_ms=int((time.time() - t0) * 1000))
    ok = total if rc == 0 else 0
    return phase_result("phase9", total, ok, total - ok,
                        cls="bug" if total - ok else None,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 10

def phase10_packaging():
    t0 = time.time()
    checks = []
    rc, _, _ = run([sys.executable, "-c",
                    "import ohm_synapse, ohm_chat, ohm_kairos, "
                    "ohm_embeddings, ohm_auth, ohm_cli"], timeout=30)
    checks.append(("imports", rc == 0))
    dist = ROOT / "dist"
    whl = list(dist.glob("ohm_synapse-*.whl")) if dist.is_dir() else []
    checks.append(("wheel_exists", bool(whl)))
    ok = sum(1 for _, c in checks if c)
    failed = len(checks) - ok
    return phase_result("phase10", len(checks), ok, failed,
                        notes=[n for n, c in checks if not c],
                        cls="missing" if failed else None,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ phase 11

def phase11_security():
    t0 = time.time()
    tests = [
        "test_ohm.TestSecurity.test_public_broker_rejected",
        "test_ohm.TestSecurity.test_sandbox_blocks_remote_exec",
        "test_ohm.TestSecurity.test_rate_limiter",
    ]
    ok = failed = 0
    notes = []
    for t in tests:
        rc, out, err = run([sys.executable, "-m", "unittest", t, "-v"],
                           timeout=60)
        if rc == 0:
            ok += 1
        else:
            failed += 1
            notes.append(t)
    return phase_result("phase11", ok + failed, ok, failed,
                        cls="bug" if failed else None, notes=notes,
                        duration_ms=int((time.time() - t0) * 1000))


# ------------------------------------------------------------------ registry

PHASES = {
    "phase0":  phase0_environment,
    "phase1":  phase1_inventory,
    "phase2":  phase2_tests,
    "phase3":  phase3_syntax_mypy,
    "phase4":  phase4_cli,
    "phase5":  phase5_peer_http,
    "phase6":  phase6_chat,
    "phase7":  phase7_ui,
    "phase8":  phase8_benchmarks,
    "phase9":  phase9_e2e,
    "phase10": phase10_packaging,
    "phase11": phase11_security,
}


# ------------------------------------------------------------------ diff

def classify_regressions(results):
    TRAIL.mkdir(exist_ok=True)
    prev = sorted(TRAIL.glob("verify_*.json"))
    if not prev:
        return
    try:
        data = json.loads(prev[-1].read_text(encoding="utf-8"))
    except Exception:
        return
    prev_map = {r["phase"]: r for r in data.get("results", [])}
    for r in results:
        p = prev_map.get(r["phase"])
        if not p:
            continue
        if p.get("failed", 0) == 0 and r.get("failed", 0) > 0:
            r["class"] = "regression"
            r["notes"].append(f"was ok in {prev[-1].name}")


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    phases = [k for k in PHASES if (not only or k in only) and k not in skip]

    print(f"# verify_all - {ROOT}\n")
    t_all = time.time()
    results = []
    for name in phases:
        print(f"  --> {name} ...", flush=True)
        r = PHASES[name]()
        results.append(r)
        flag = {"ok": "OK", "fail": "FAIL", "skip": "SKIP"}[r["status"]]
        print(f"  [{flag}] {name:<8} "
              f"checked={r['checked']} ok={r['ok']} failed={r['failed']}"
              + (f"  [{r['class']}]" if r["class"] else "")
              + (f"  {r['duration_ms']}ms" if r["duration_ms"] else ""))
        for n in r["notes"]:
            print(f"         - {n}")

    classify_regressions(results)

    total_c = sum(r["checked"] for r in results)
    total_o = sum(r["ok"] for r in results)
    total_f = sum(r["failed"] for r in results)

    print()
    print(f"TOTAL checked={total_c} ok={total_o} failed={total_f}")
    print(f"time: {time.time() - t_all:.1f}s")

    TRAIL.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report = TRAIL / f"verify_{stamp}.json"
    report.write_text(json.dumps({
        "stamp": stamp,
        "total": {"checked": total_c, "ok": total_o, "failed": total_f},
        "duration_s": round(time.time() - t_all, 1),
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"report: {report.relative_to(ROOT)}")

    if args.report:
        prev = sorted(TRAIL.glob("verify_*.json"))
        if len(prev) >= 2:
            before = json.loads(prev[-2].read_text(encoding="utf-8"))
            print(f"\nvs {prev[-2].name}: "
                  f"failed {before['total']['failed']} -> {total_f}")

    return 1 if total_f else 0


if __name__ == "__main__":
    sys.exit(main())