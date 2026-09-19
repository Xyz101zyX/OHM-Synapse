"""Fix verify_all.py: unbuffered child output, show all lines.

Root cause: run_tests.py writes to a pipe; Python block-buffers stdout
when not attached to a TTY, so nothing appears until the process exits.

Fix: pass PYTHONUNBUFFERED=1 to child env, and print every line from
child stdout (not just filtered checkpoints).
"""

import ast
import pathlib
import shutil
import sys

TARGET = pathlib.Path("verify_all.py")
BACKUP = pathlib.Path("verify_all.py.before_stream_fix")

if not TARGET.exists():
    print("[abort] verify_all.py not found")
    sys.exit(1)

shutil.copy(TARGET, BACKUP)
src = TARGET.read_text(encoding="utf-8")

# ---------------------------------------------------------------- patch
OLD = '''def run_stream(cmd, timeout=1200, progress_prefix="    "):
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
            if any(s in line for s in ("[", "Ran ", "OK", "FAILED",
                                        "elapsed=", "/120]", "/tests]")):
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
        return 124, "".join(buf) + f"\\n[stream error: {e}]"
    return proc.returncode, "".join(buf)'''

NEW = '''def run_stream(cmd, timeout=1200, progress_prefix="    "):
    """Run cmd, stream stdout+stderr live, return (rc, full_output)."""
    import os as _os
    import subprocess as _sp
    env = dict(_os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8:replace"
    proc = _sp.Popen(cmd, cwd=ROOT, stdout=_sp.PIPE, stderr=_sp.STDOUT,
                     text=True, encoding="utf-8", errors="replace",
                     bufsize=1, env=env)
    buf = []
    try:
        for line in proc.stdout:
            buf.append(line)
            stripped = line.rstrip()
            if stripped and len(stripped) < 160:
                print(f"{progress_prefix}{stripped}", flush=True)
        proc.wait(timeout=timeout)
    except Exception as e:
        proc.kill()
        return 124, "".join(buf) + f"\\n[stream error: {e}]"
    return proc.returncode, "".join(buf)'''

if OLD not in src:
    print("[abort] run_stream block not found verbatim")
    print("--- current run_stream ---")
    i = src.find("def run_stream")
    j = src.find("\ndef ", i + 10)
    print(src[i:j])
    sys.exit(1)

src = src.replace(OLD, NEW, 1)
print("[patch] run_stream: PYTHONUNBUFFERED=1 + show all child lines")

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"[abort] syntax error: {e}")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("[ok] wrote verify_all.py")	