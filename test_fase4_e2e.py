import os
os.environ["OHM_TEST_MODE"] = "0"

import sys
import time
import json
import shutil
import signal
import subprocess
import unittest
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).parent
RUN_PEER = HERE / "run_peer.py"
BROKER = HERE / "run_local_broker.py"
DATA_DIR = HERE / "ohm_data"


def http_get(port, path, timeout=5):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post(port, path, payload, timeout=10):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_ready(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            http_get(port, "/ping", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def wait_status(port, predicate, timeout=20, label=""):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = http_get(port, "/status", timeout=3)
            if predicate(last):
                return True, last
        except Exception as e:
            last = {"error": str(e)}
        time.sleep(0.5)
    return False, last


class TestE2ESubprocess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.broker_proc = None
        cls.peer_a = None
        cls.peer_b = None
        cls.port_a = 7870
        cls.port_b = 7871
        cls.node_a = None
        cls.node_b = None

        # Check broker reachable
        import socket
        s = socket.socket()
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", 1883))
            s.close()
            cls.broker_available = True
        except Exception:
            cls.broker_available = False
        if not cls.broker_available:
            return

        # Reset data dirs
        for name in ("e2e_a", "e2e_b"):
            p = DATA_DIR / name
            if p.exists():
                shutil.rmtree(p)

        cls.peer_a = subprocess.Popen(
            [sys.executable, str(RUN_PEER), "--name", "e2e_a",
             "--port", str(cls.port_a), "--headless"],
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        cls.peer_b = subprocess.Popen(
            [sys.executable, str(RUN_PEER), "--name", "e2e_b",
             "--port", str(cls.port_b), "--headless"],
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert wait_ready(cls.port_a, timeout=45), "peer A did not start"
        assert wait_ready(cls.port_b, timeout=45), "peer B did not start"

        cls.node_a = http_get(cls.port_a, "/status")["node_id"]
        cls.node_b = http_get(cls.port_b, "/status")["node_id"]

    @classmethod
    def tearDownClass(cls):
        for p in (cls.peer_a, cls.peer_b):
            if p is None:
                continue
            if p.poll() is None:
                try:
                    p.send_signal(signal.SIGTERM)
                    p.wait(timeout=8)
                except Exception:
                    p.kill()
        for name in ("e2e_a", "e2e_b"):
            p = DATA_DIR / name
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    def setUp(self):
        if not self.broker_available:
            self.skipTest("MQTT broker not running on localhost:1883")

    def test_01_peers_are_distinct_processes(self):
        self.assertNotEqual(self.node_a, self.node_b)
        self.assertNotEqual(self.peer_a.pid, self.peer_b.pid)
        self.assertIsNone(self.peer_a.poll(), "peer A crashed")
        self.assertIsNone(self.peer_b.poll(), "peer B crashed")

    def test_02_discovery_via_mqtt(self):
        ok, status = wait_status(
            self.port_a,
            lambda s: self.node_b in s.get("known_peers", []),
            timeout=20,
            label="A sees B",
        )
        self.assertTrue(ok, f"A did not discover B. Status: {status}")

    def test_03_chat_handshake_across_processes(self):
        r = http_post(self.port_a, "/chat_handshake", {"peer": self.node_b})
        self.assertTrue(r.get("ok"))

        ok, status = wait_status(
            self.port_a,
            lambda s: self.node_b in s.get("peers", []),
            timeout=15,
            label="A has session with B",
        )
        self.assertTrue(ok, f"A session missing. Status: {status}")

    def test_04_chat_message_cross_process(self):
        # Ensure handshake happened first
        if self.node_b not in http_get(self.port_a, "/status").get("peers", []):
            http_post(self.port_a, "/chat_handshake", {"peer": self.node_b})
            wait_status(
                self.port_a,
                lambda s: self.node_b in s.get("peers", []),
                timeout=15,
            )

        msg = "hello cross-process"
        r = http_post(self.port_a, "/chat_send",
                      {"peer": self.node_b, "message": msg})
        self.assertEqual(r.get("status"), "SENT", f"send failed: {r}")

        ok, _ = wait_status(
            self.port_b,
            lambda s: True,
            timeout=1,
        )
        deadline = time.time() + 15
        found = False
        while time.time() < deadline:
            hist = http_post(self.port_b, "/chat_history",
                             {"peer": self.node_a}).get("history", [])
            if any(msg in (h.get("content") or "") for h in hist):
                found = True
                break
            time.sleep(0.5)
        self.assertTrue(found, "message did not arrive at peer B")

    def test_05_memory_sync_across_processes(self):
        r = http_post(self.port_a, "/think",
                      {"query": "/remember my cat name is Zeca"})
        self.assertIn(r["status"], ("REMEMBER", "OK"))

        deadline = time.time() + 20
        synced = False
        while time.time() < deadline:
            st = http_get(self.port_b, "/status")
            mem_path = DATA_DIR / "e2e_b" / "mem.json"
            if mem_path.exists():
                try:
                    data = json.loads(mem_path.read_text(encoding="utf-8"))
                    if any("zeca" in (v.get("content", "") or "").lower()
                           for v in data.values()):
                        synced = True
                        break
                except Exception:
                    pass
            time.sleep(1)
        self.assertTrue(synced, "personal record did not sync to peer B")

    def test_06_shutdown_clean(self):
        r = http_post(self.port_a, "/quit", {})
        self.assertTrue(r.get("ok"))
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.peer_a.poll() is not None:
                break
            time.sleep(0.3)
        self.assertIsNotNone(self.peer_a.poll(), "peer A did not exit on quit")


if __name__ == "__main__":
    unittest.main(verbosity=2)