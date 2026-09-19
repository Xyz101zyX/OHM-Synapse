import os
import sys
import json
import time
import signal
import argparse
import subprocess
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List

from ohm_auth import AuthManager, auth_disabled_by_env, SESSION_TTL_SECONDS

OHM_HOME = Path(os.environ.get("OHM_HOME", Path.home() / ".ohm"))
REGISTRY_FILE = OHM_HOME / "registry.json"
VERSION = "0.0.1"


def ensure_home() -> Path:
    OHM_HOME.mkdir(parents=True, exist_ok=True)
    return OHM_HOME


def load_registry() -> Dict[str, Any]:
    ensure_home()
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_registry(data: Dict[str, Any]) -> None:
    ensure_home()
    tmp = REGISTRY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, REGISTRY_FILE)


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle == 0:
                return False
            kernel32.CloseHandle(handle)
            return True
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def find_free_port(start: int = 7860, end: int = 7960) -> int:
    import socket
    for p in range(start, end):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            continue
    raise RuntimeError(f"no free port in range {start}-{end}")


def http_get(port: int, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, method="GET")
        _tok = os.environ.get("OHM_AUTH_TOKEN", "")
        if _tok:
            req.add_header("Authorization", f"Bearer {_tok}")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def http_post(port: int, path: str, payload: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    token = os.environ.get("OHM_AUTH_TOKEN", "")
    try:
        url = f"http://127.0.0.1:{port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        _tok = os.environ.get("OHM_AUTH_TOKEN", "")
        if _tok:
            req.add_header("Authorization", f"Bearer {_tok}")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _session_dir() -> Path:
    p = OHM_HOME / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _session_file(name: str) -> Path:
    return _session_dir() / f"{name}.token"


def _load_session_token(name: str) -> str:
    f = _session_file(name)
    if not f.exists():
        return ""
    try:
        return f.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _save_session_token(name: str, token: str) -> None:
    _session_file(name).write_text(token, encoding="utf-8")


def _clear_session_token(name: str) -> None:
    f = _session_file(name)
    if f.exists():
        f.unlink()


def peer_dir(name: str) -> Path:
    return OHM_HOME / "peers" / name


def cmd_init(args: argparse.Namespace) -> int:
    name = args.name
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        print(f"error: invalid peer name '{name}'. Use alphanumeric, dash, underscore.")
        return 2

    pdir = peer_dir(name)
    if pdir.exists() and not args.force:
        print(f"peer '{name}' already exists at {pdir}")
        print("use --force to reinitialize (will wipe existing data)")
        return 1

    if pdir.exists() and args.force:
        shutil.rmtree(pdir)

    pdir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "name": name,
        "created": time.time(),
        "version": VERSION,
        "port": None,
    }
    (pdir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    print(f"[ok] peer '{name}' initialized at {pdir}")
    print()
    print("next steps:")
    print(f"  1. start broker:    ohm broker")
    print(f"  2. start peer:      ohm run {name}")
    print(f"  3. check status:    ohm status {name}")
    print()
    print(f"data dir: {pdir}")
    return 0


def _spawn_peer(name: str, port: int, headless: bool, extra: list[str] | None = None,
                extra_env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    pdir = peer_dir(name)
    if not pdir.exists():
        raise RuntimeError(f"peer '{name}' not initialized. run: ohm init {name}")

    env = os.environ.copy()
    env["OHM_HOME"] = str(OHM_HOME)
    if extra_env:
        env.update(extra_env)

    cmd = [
        sys.executable, "-m", "run_peer",
        "--name", name,
        "--port", str(port),
        "--data-dir", str(pdir),
    ]
    if headless:
        cmd.append("--headless")
    if extra:
        cmd.extend(extra)

    proc = subprocess.Popen(cmd, env=env)
    return proc


def cmd_run(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized. run: ohm init {name}")
        return 1

    port = args.port or find_free_port()
    auth = AuthManager(pdir)
    reg = load_registry()
    if name in reg and is_pid_alive(reg[name].get("pid", 0)):
        print(f"error: peer '{name}' already running (pid {reg[name]['pid']}, port {reg[name].get('port')})")
        print("stop it first, or use a different name")
        return 1

    headless = args.headless

    print(f"[ohm] starting peer '{name}' on port {port}{' (headless)' if headless else ''}")
    if not headless and auth.configured:
        print(f"[ohm] UI will ask for password when opened in browser")
    proc = _spawn_peer(name, port, headless)

    reg[name] = {
        "port": port,
        "pid": proc.pid,
        "started": time.time(),
        "headless": headless,
    }
    save_registry(reg)

    if headless:
        wait_ready(port, timeout=60)
        print(f"[ohm] peer '{name}' ready at http://127.0.0.1:{port}")
        print(f"[ohm] to stop: ohm stop {name}")
        print(f"[ohm] to chat: ohm chat {name} <peer_node_id> \"<message>\"")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=8)
    else:
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=8)

    reg = load_registry()
    reg.pop(name, None)
    save_registry(reg)
    return 0


def wait_ready(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_get(port, "/ping", timeout=2):
            return True
        time.sleep(0.5)
    return False


def cmd_stop(args: argparse.Namespace) -> int:
    name = args.name
    reg = load_registry()
    if name not in reg:
        print(f"peer '{name}' not in registry")
        return 1
    entry = reg[name]
    pid = entry.get("pid", 0)
    port = entry.get("port")

    if not is_pid_alive(pid):
        print(f"peer '{name}' (pid {pid}) already stopped")
        reg.pop(name, None)
        save_registry(reg)
        return 0

    if port:
        http_post(port, "/quit", {}, timeout=3)

    deadline = time.time() + 8
    while time.time() < deadline and is_pid_alive(pid):
        time.sleep(0.3)

    if is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(1)

    reg.pop(name, None)
    save_registry(reg)
    print(f"[ok] peer '{name}' stopped")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    name = args.name
    reg = load_registry()
    if name not in reg:
        print(f"peer '{name}' not running")
        return 1
    entry = reg[name]
    port = entry.get("port")
    pid = entry.get("pid", 0)

    if not is_pid_alive(pid):
        print(f"peer '{name}' (pid {pid}) is dead; cleaning registry")
        reg.pop(name, None)
        save_registry(reg)
        return 1

    st = http_get(port, "/status")
    if st is None:
        print(f"peer '{name}' alive (pid {pid}) but HTTP not responding on {port}")
        return 1

    if args.json:
        print(json.dumps(st, indent=2, default=str))
        return 0

    print(f"peer:      {name}")
    print(f"node_id:   {st.get('node_id')}")
    print(f"port:      {port}")
    print(f"pid:       {pid}")
    print(f"mqtt:      {st.get('mqtt')}")
    print(f"chat:      {st.get('chat')}")
    print(f"sessions:  {st.get('sessions')}")
    print(f"contacts:  {st.get('contacts')}")
    print(f"peers:     {st.get('peers')}")
    print(f"known:     {st.get('known_peers')}")
    print(f"thresholds:")
    for k, v in (st.get("thresholds") or {}).items():
        print(f"  {k}: {v}")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    name = args.name
    reg = load_registry()
    if name not in reg:
        print(f"peer '{name}' not running")
        return 1
    entry = reg[name]
    port = entry.get("port")
    peer = args.peer
    message = args.message
    pdir = peer_dir(name)
    auth = AuthManager(pdir)
    if auth.configured:
        token = _load_session_token(name)
        if not token or not auth.validate_session(token):
            print(f"error: not logged in to '{name}'. run: ohm login {name}")
            return 1
        os.environ["OHM_AUTH_TOKEN"] = token

    hs = http_post(port, "/chat_handshake", {"peer": peer})
    if hs is None:
        print("error: handshake failed")
        return 1

    time.sleep(1.5)

    r = http_post(port, "/chat_send", {"peer": peer, "message": message})
    if r is None:
        print("error: send failed")
        return 1

    status = r.get("status")
    if status == "SENT":
        print(f"[ok] sent to {peer[:8]}...")
        return 0
    elif status == "HANDSHAKE_SENT":
        print(f"[~] handshake sent; retry in 2s")
        time.sleep(2)
        r2 = http_post(port, "/chat_send", {"peer": peer, "message": message})
        if r2 and r2.get("status") == "SENT":
            print(f"[ok] sent to {peer[:8]}...")
            return 0
    print(f"[x] status: {status}  detail: {r}")
    return 1


def cmd_broker(args: argparse.Namespace) -> int:
    print("[ohm] starting local MQTT broker on tcp://0.0.0.0:1883")
    print("[ohm] Ctrl+C to stop")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "run_local_broker"],
            env=os.environ.copy(),
        )
        proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=8)
    return 0


def cmd_two_peers(args: argparse.Namespace) -> int:
    for name in (args.name_a, args.name_b):
        pdir = peer_dir(name)
        if not pdir.exists():
            print(f"[init] creating peer '{name}'")
            ns = argparse.Namespace(name=name, force=False)
            cmd_init(ns)

    port_a = args.port_a or find_free_port(7860, 7900)
    port_b = args.port_b or find_free_port(port_a + 1, port_a + 40)

    print(f"[ohm] peer-a: {args.name_a} on port {port_a}")
    print(f"[ohm] peer-b: {args.name_b} on port {port_b}")

    proc_a = _spawn_peer(args.name_a, port_a, args.headless)
    time.sleep(2)
    proc_b = _spawn_peer(args.name_b, port_b, args.headless)

    reg = load_registry()
    reg[args.name_a] = {"port": port_a, "pid": proc_a.pid, "started": time.time(), "headless": args.headless}
    reg[args.name_b] = {"port": port_b, "pid": proc_b.pid, "started": time.time(), "headless": args.headless}
    save_registry(reg)

    if args.headless:
        wait_ready(port_a, 60)
        wait_ready(port_b, 60)
        st_a = http_get(port_a, "/status")
        st_b = http_get(port_b, "/status")
        print()
        print(f"peer-a node_id: {st_a.get('node_id') if st_a else '?'}")
        print(f"peer-b node_id: {st_b.get('node_id') if st_b else '?'}")
        print()
        print("run in another terminal:")
        print(f"  ohm chat {args.name_a} {st_b.get('node_id') if st_b else '<peer-b>'} \"hello\"")
        print()
        print("Ctrl+C to stop both")
        try:
            proc_a.wait()
        except KeyboardInterrupt:
            pass
    else:
        try:
            proc_a.wait()
        except KeyboardInterrupt:
            pass

    for p in (proc_a, proc_b):
        if p.poll() is None:
            try:
                p.send_signal(signal.SIGINT)
                p.wait(timeout=5)
            except Exception:
                p.kill()

    reg = load_registry()
    reg.pop(args.name_a, None)
    reg.pop(args.name_b, None)
    save_registry(reg)
    return 0


def _prompt_password(confirm: bool = True) -> str:
    import getpass
    pw = getpass.getpass("Password: ")
    if confirm:
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("error: passwords do not match")
            return ""
    return pw


def cmd_setup_auth(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized. run: ohm init {name}")
        return 1
    auth = AuthManager(pdir)
    if auth.configured and not args.force:
        print(f"auth already configured for '{name}'. use --force to reconfigure.")
        return 1
    print(f"[ohm auth setup for '{name}']")
    pw = _prompt_password(confirm=True)
    if not pw:
        return 2
    print()
    print("Now set 3 personal recovery questions.")
    print("These are used to reset your password if you forget it.")
    print()
    questions = []
    for i in range(1, 4):
        q = input(f"Question {i}: ").strip()
        a = input(f"Answer   {i}: ").strip()
        questions.append((q, a))
    try:
        phrase = auth.configure(pw, questions)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print()
    print("=" * 60)
    print("  RECOVERY PHRASE - WRITE THIS DOWN NOW")
    print("=" * 60)
    print()
    print(f"    {phrase}")
    print()
    print("This phrase is shown only once. It is the LAST RESORT")
    print("for password recovery if you also forget all 3 answers.")
    print("=" * 60)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized")
        return 1
    auth = AuthManager(pdir)
    if not auth.configured:
        print(f"peer '{name}' has no auth configured; skipping")
        return 0
    import getpass
    pw = getpass.getpass(f"Password for '{name}': ")
    if not auth.verify_password(pw):
        print("error: invalid password")
        return 1
    token = auth.create_session()
    _save_session_token(name, token)
    print(f"[ok] logged in as '{name}'")
    print(f"token expires in {SESSION_TTL_SECONDS // 3600}h")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized")
        return 1
    auth = AuthManager(pdir)
    token = _load_session_token(name)
    if token:
        auth.revoke_session(token)
    _clear_session_token(name)
    print(f"[ok] logged out from '{name}'")
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized")
        return 1
    auth = AuthManager(pdir)
    if not auth.configured:
        print(f"peer '{name}' has no auth configured")
        return 0
    print(f"recovery for '{name}'")
    print("choose method:")
    print("  1. answer 3 personal questions")
    print("  2. use recovery phrase")
    choice = input("method [1/2]: ").strip()
    ok = False
    if choice == "1":
        answers = []
        for i, q in enumerate(auth.get_questions(), 1):
            a = input(f"  {q}  ").strip()
            answers.append(a)
        ok = auth.verify_answers(answers)
    elif choice == "2":
        phrase = input("recovery phrase: ").strip()
        ok = auth.verify_recovery_phrase(phrase)
    else:
        print("invalid choice")
        return 2
    if not ok:
        print("error: verification failed")
        return 1
    import getpass
    new_pw = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm: ")
    if new_pw != confirm:
        print("error: passwords do not match")
        return 1
    try:
        auth.reset_password(new_pw)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print(f"[ok] password reset; all sessions revoked")
    return 0


def cmd_auth_status(args: argparse.Namespace) -> int:
    name = args.name
    pdir = peer_dir(name)
    if not pdir.exists():
        print(f"error: peer '{name}' not initialized")
        return 1
    auth = AuthManager(pdir)
    st = auth.status()
    if args.json:
        print(json.dumps(st, indent=2))
        return 0
    print(f"peer:       {name}")
    print(f"configured: {st['configured']}")
    print(f"questions:  {st['questions_count']}")
    print(f"sessions:   {st['sessions']}")
    if st['configured']:
        for q in auth.get_questions():
            print(f"  - {q}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    reg = load_registry()
    if not reg:
        print("no peers registered")
        return 0
    print(f"{'name':20} {'port':>6} {'pid':>8} {'alive':>6}")
    print("-" * 44)
    for name, entry in sorted(reg.items()):
        pid = entry.get("pid", 0)
        port = entry.get("port", "?")
        alive = "yes" if is_pid_alive(pid) else "no"
        print(f"{name:20} {str(port):>6} {pid:>8} {alive:>6}")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(f"ohm-synapse {VERSION}")
    print(f"python {sys.version.split()[0]}")
    print(f"data home: {OHM_HOME}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ohm",
        description="OHM-Synapse — epistemic digital twin",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ohm init alice\n"
            "  ohm broker\n"
            "  ohm run alice\n"
            "  ohm two-peers\n"
            "  ohm chat alice <peer_node_id> \"hello\"\n"
            "  ohm status alice\n"
            "  ohm list\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="initialize a peer data directory")
    p_init.add_argument("name", help="peer name")
    p_init.add_argument("--force", action="store_true", help="wipe existing data")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="start a peer")
    p_run.add_argument("name", help="peer name")
    p_run.add_argument("--port", type=int, default=None, help="HTTP port (auto if omitted)")
    p_run.add_argument("--headless", action="store_true", help="no gradio UI, only HTTP API")
    p_run.set_defaults(func=cmd_run)

    p_stop = sub.add_parser("stop", help="stop a running peer")
    p_stop.add_argument("name")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="show peer status")
    p_status.add_argument("name")
    p_status.add_argument("--json", action="store_true", help="raw JSON output")
    p_status.set_defaults(func=cmd_status)

    p_chat = sub.add_parser("chat", help="send a chat message to a peer")
    p_chat.add_argument("name", help="local peer name")
    p_chat.add_argument("peer", help="target node_id (hex)")
    p_chat.add_argument("message", help="message text")
    p_chat.set_defaults(func=cmd_chat)

    p_broker = sub.add_parser("broker", help="start local MQTT broker")
    p_broker.set_defaults(func=cmd_broker)

    p_two = sub.add_parser("two-peers", help="start two peers for local testing")
    p_two.add_argument("--name-a", default="peer-a", help="first peer name")
    p_two.add_argument("--name-b", default="peer-b", help="second peer name")
    p_two.add_argument("--port-a", type=int, default=None)
    p_two.add_argument("--port-b", type=int, default=None)
    p_two.add_argument("--headless", action="store_true")
    p_two.set_defaults(func=cmd_two_peers)

    p_auth = sub.add_parser("setup-auth", help="configure password + 3 questions + recovery phrase")
    p_auth.add_argument("name")
    p_auth.add_argument("--force", action="store_true")
    p_auth.set_defaults(func=cmd_setup_auth)

    p_login = sub.add_parser("login", help="login to a peer")
    p_login.add_argument("name")
    p_login.set_defaults(func=cmd_login)

    p_logout = sub.add_parser("logout", help="logout from a peer")
    p_logout.add_argument("name")
    p_logout.set_defaults(func=cmd_logout)

    p_recover = sub.add_parser("recover", help="recover password via questions or phrase")
    p_recover.add_argument("name")
    p_recover.set_defaults(func=cmd_recover)

    p_auth_st = sub.add_parser("auth-status", help="show auth status")
    p_auth_st.add_argument("name")
    p_auth_st.add_argument("--json", action="store_true")
    p_auth_st.set_defaults(func=cmd_auth_status)

    p_list = sub.add_parser("list", help="list registered peers")
    p_list.set_defaults(func=cmd_list)

    p_ver = sub.add_parser("version", help="show version")
    p_ver.set_defaults(func=cmd_version)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())