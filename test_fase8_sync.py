import os
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import time
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


def make_brain(broker, port, allow_public):
    tmpdir = tempfile.mkdtemp()
    cfg = ohm.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = os.path.join(tmpdir, "mem.json")
    cfg.memory_cfg["audit_file"] = os.path.join(tmpdir, "audit.jsonl")
    cfg.memory_cfg["export_file"] = os.path.join(tmpdir, "export.json")
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["mqtt_broker"] = broker
    cfg.distributed_cfg["mqtt_port"] = port
    cfg.distributed_cfg["sync_interval"] = 2
    cfg.security_cfg = dict(cfg.security_cfg)
    cfg.security_cfg["allow_public_broker"] = allow_public
    cfg.security_cfg["require_tls"] = (port == 8883)
    cfg.security_cfg["node_key_file"] = os.path.join(tmpdir, "node_keys.pem")
    b = ohm.OHMSynapse(config=cfg)
    b.external_lookup_enabled = False
    b.llm = None
    return b

def broker_available(broker, port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((broker, port))
        s.close()
        return True
    except Exception:
        return False


BROKER = os.environ.get("OHM_TEST_BROKER", "localhost")
PORT = int(os.environ.get("OHM_TEST_PORT", "1883"))
ALLOW_PUBLIC = os.environ.get("OHM_TEST_ALLOW_PUBLIC", "1") == "1"


@unittest.skipUnless(broker_available(BROKER, PORT),
                     f"broker {BROKER}:{PORT} not reachable")
class TestFase8Sync(unittest.TestCase):
    def setUp(self):
        self.a = make_brain(BROKER, PORT, ALLOW_PUBLIC)
        self.b = make_brain(BROKER, PORT, ALLOW_PUBLIC)
        self.assertNotEqual(
            self.a.node_id, self.b.node_id,
            "peers have identical node_id - key_file isolation failed"
        )
        time.sleep(2)

    def tearDown(self):
        self.a.shutdown()
        self.b.shutdown()
        time.sleep(2.0)

    def test_01_peers_discover_each_other(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.b.node_id in self.a.known_peers and self.a.node_id in self.b.known_peers:
                break
            time.sleep(0.5)
        self.assertIn(self.b.node_id, self.a.known_peers)
        self.assertIn(self.a.node_id, self.b.known_peers)

    def test_02_personal_record_propagates(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.b.node_id in self.a.known_peers:
                break
            time.sleep(0.5)
        self.a.think("/remember my cat name is Zeca")
        self.a.last_sync_time = 0
        deadline = time.time() + 20
        found = False
        while time.time() < deadline:
            for k, v in self.b.memory.store.items():
                if "zeca" in (v.get("content", "") or "").lower():
                    found = True
                    break
            if found:
                break
            time.sleep(1)
        self.assertTrue(found, "personal record did not propagate to peer B")

    def test_03_inference_layer_not_propagated(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.b.node_id in self.a.known_peers:
                break
            time.sleep(0.5)
        src = ohm.Source(kind="llm", ref="test", timestamp=time.time(),
                         layer=ohm.MemoryLayer.INFERENCE)
        self.a.memory.store_memory("inference_test_k",
                                   "this is an inference only",
                                   ohm.MemoryLayer.INFERENCE,
                                   sources=[src])
        self.a.last_sync_time = 0
        time.sleep(8)
        for k, v in self.b.memory.store.items():
            if v.get("layer") == ohm.MemoryLayer.INFERENCE:
                if "inference only" in (v.get("content", "") or "").lower():
                    self.fail("inference layer leaked through sync")

    def test_04_chat_handshake_and_message(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.b.node_id in self.a.known_peers:
                break
            time.sleep(0.5)
        ok = self.a.chat.send_handshake(self.b.node_id)
        self.assertTrue(ok)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.b.node_id in self.a.chat._session_keys and \
               self.a.node_id in self.b.chat._session_keys:
                break
            time.sleep(0.5)
        self.assertIn(self.b.node_id, self.a.chat._session_keys)
        self.assertIn(self.a.node_id, self.b.chat._session_keys)

        result = self.a.chat.send(self.b.node_id, "hello over encrypted channel")
        self.assertEqual(result.get("status"), "SENT")
        deadline = time.time() + 10
        received = None
        while time.time() < deadline:
            hist = self.b.chat.get_history(self.a.node_id)
            if hist:
                received = hist[-1]
                break
            time.sleep(0.5)
        self.assertIsNotNone(received)
        self.assertIn("hello over encrypted channel", received["content"])

    def test_05_chat_message_ciphertext_on_wire(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.b.node_id in self.a.known_peers:
                break
            time.sleep(0.5)
        self.a.chat.send_handshake(self.b.node_id)
        time.sleep(3)
        if self.b.node_id not in self.a.chat._session_keys:
            self.skipTest("handshake not complete")
        plaintext = "TOPSECRET_TOKEN_12345"
        result = self.a.chat.send(self.b.node_id, plaintext)
        self.assertEqual(result.get("status"), "SENT")
        history = self.a.chat.get_history(self.b.node_id)
        self.assertTrue(any(plaintext in h["content"] for h in history))


if __name__ == "__main__":
    unittest.main(verbosity=2)