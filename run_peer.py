import os
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import base64
import time
import json
import signal
import shutil
import argparse
import threading
from pathlib import Path
import gradio as gr
from ohm_auth import AuthManager, auth_disabled_by_env
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_brain(name, reset=False, data_dir=None):
    if data_dir is None:
        data_dir = HERE / "ohm_data" / name
    else:
        data_dir = Path(data_dir)
    if reset and data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    cfg = mod.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = str(data_dir / "mem.json")
    cfg.memory_cfg["audit_file"] = str(data_dir / "audit.jsonl")
    cfg.memory_cfg["export_file"] = str(data_dir / "export.json")
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["mqtt_broker"] = "localhost"
    cfg.distributed_cfg["mqtt_port"] = 1883
    cfg.distributed_cfg["sync_interval"] = 3
    cfg.security_cfg = dict(cfg.security_cfg)
    cfg.security_cfg["require_tls"] = False
    cfg.security_cfg["allow_public_broker"] = True
    cfg.security_cfg["node_key_file"] = str(data_dir / "node_keys.pem")

    if os.environ.get("OHM_TEST_MODE") == "1":
        cfg.llm_cfg = dict(cfg.llm_cfg)
        cfg.llm_cfg["enabled"] = False

    b = mod.OHMSynapse(config=cfg)
    if os.environ.get("OHM_TEST_MODE") == "1":
        b.llm = None
    b.external_lookup_enabled = False
    return b


class Handler(BaseHTTPRequestHandler):
    brain: Any = None
    auth: AuthManager | None = None

    def log_message(self, fmt, *args):
        pass

    def _check_auth(self) -> bool:
        if self.auth is None or not self.auth.configured:
            return True
        if auth_disabled_by_env():
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        token = header[len("Bearer "):].strip()
        self.auth._load()
        return self.auth.validate_session(token)

    def _json(self, code, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        if self.path in ("/ping", "/health"):
            self._json(200, {"ok": True})
            return
        if not self._check_auth():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path == "/status":
            s = self.brain.chat.status()
            self._json(200, {
                "node_id": self.brain.node_id,
                "mqtt": self.brain.mqtt.enabled,
                "chat": s["enabled"],
                "sessions": s["active_sessions"],
                "peers": s["peers"],
                "contacts": s["contacts"],
                "known_peers": list(self.brain.known_peers.keys()),
                "thresholds": dict(self.brain.thresholds),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()
        if self.path == "/auth/login":
            if self.auth is None or not self.auth.configured:
                self._json(400, {"error": "auth not configured"})
                return
            pw = body.get("password", "")
            if not self.auth.verify_password(pw):
                self._json(401, {"error": "invalid credentials"})
                return
            token = self.auth.create_session()
            self._json(200, {"token": token})
            return
        if self.path == "/auth/logout":
            header = self.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                token = header[7:].strip()
                if self.auth:
                    self.auth.revoke_session(token)
            self._json(200, {"ok": True})
            return
        if not self._check_auth():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path == "/think":
            query = body.get("query", "")
            resp = self.brain.think(query, origin="http")
            self._json(200, {
                "status": resp.status,
                "text": resp.text,
                "confidence": resp.confidence,
                "layer": resp.layer,
                "llm_used": resp.llm_used,
            })
        elif self.path == "/chat_handshake":
            peer = body.get("peer", "")
            ok = self.brain.chat.send_handshake(peer)
            self._json(200, {"ok": ok, "peer": peer})
        elif self.path == "/chat_send":
            peer = body.get("peer", "")
            msg = body.get("message", "")
            result = self.brain.chat.send(peer, msg)
            self._json(200, result)
        elif self.path == "/chat_history":
            peer = body.get("peer", "")
            hist = self.brain.chat.get_history(peer)
            self._json(200, {"history": hist})
        elif self.path == "/quit":
            self._json(200, {"ok": True})
            threading.Thread(target=lambda: os.kill(os.getpid(), signal.SIGTERM), daemon=True).start()
        else:
            self._json(404, {"error": "not found"})



def run_http(brain, port):
    Handler.brain = brain
    try:
        pdir = Path(brain.config.memory_cfg.get("persistence_file", "./mem.json")).parent
        Handler.auth = AuthManager(pdir)
    except Exception:
        Handler.auth = None
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    print(f"[http] listening on 127.0.0.1:{port}", flush=True)

    def stop(signum, frame):
        print("[http] shutting down", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _install_auth_middleware(demo, auth, name):
    if auth is None or not auth.configured:
        print(f"[{name}] UI auth: not configured", flush=True)
        return
    try:
        from fastapi import Request
        from fastapi.responses import Response as FastResponse
    except ImportError:
        print(f"[{name}] UI auth: fastapi not available", flush=True)
        return
    app = getattr(demo, "app", None)
    if app is None:
        print(f"[{name}] UI auth: demo.app not available", flush=True)
        return
    PUBLIC_PATHS = ("/ping", "/health", "/favicon.ico")
    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if not header.startswith("Basic "):
            return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            user, _, pw = decoded.partition(":")
        except Exception:
            return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
        if not auth.verify_password(pw):
            return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
        return await call_next(request)
    print(f"[{name}] UI auth enabled (user: any, password: as configured)", flush=True)


def run_gradio(brain, name, port):
    from ohm_ui import build_ui, CUSTOM_CSS
    _auth: AuthManager | None = None
    try:
        _pdir = Path(brain.config.memory_cfg.get("persistence_file", "./mem.json")).parent
        _auth = AuthManager(_pdir)
    except Exception:
        _auth = None
    demo = build_ui(brain, name, port)
    _install_auth_middleware(demo, _auth, name)
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        quiet=False,
        prevent_thread_lock=False,
        css=CUSTOM_CSS,
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    brain = make_brain(args.name, reset=args.reset, data_dir=args.data_dir)

    print(f"[{args.name}] node_id = {brain.node_id}", flush=True)
    print(f"[{args.name}] port = {args.port}", flush=True)
    print(f"[{args.name}] mqtt_enabled = {brain.mqtt.enabled}", flush=True)
    print(f"[{args.name}] chat_enabled = {brain.chat.enabled}", flush=True)
    print(f"[{args.name}] mode = {'headless' if args.headless else 'gradio'}", flush=True)

    try:
        if args.headless:
            run_http(brain, args.port)
        else:
            run_gradio(brain, args.name, args.port)
    except KeyboardInterrupt:
        pass
    finally:
        brain.shutdown()


if __name__ == "__main__":
    main()
