import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import time
import json
import base64
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

from ohm_chat import OHMChat


class FakeMQTT:
    def __init__(self):
        self.published = []
        self.client = None
        self.enabled = False
    def publish(self, topic, payload, qos=1):
        self.published.append((topic, payload))


class FakeBrain:
    def __init__(self, data_dir):
        self.config = ohm.OHMConfig()
        self.config.memory_cfg = dict(self.config.memory_cfg)
        self.config.memory_cfg["persistence_file"] = str(Path(data_dir) / "mem.json")
        self.config.raw["chat"] = {"session_ttl_seconds": 3600}


def make_chat(tmpdir, node_id="nodeA"):
    brain = FakeBrain(tmpdir)
    mqtt = FakeMQTT()
    return OHMChat(brain, mqtt, node_id)


class TestECDHPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_ecdh_key_created(self):
        chat = make_chat(self.tmpdir)
        self.assertIsNotNone(chat._private_key)
        self.assertTrue(chat.public_pem.startswith("-----BEGIN PUBLIC KEY-----"))

    def test_ecdh_key_persisted_to_disk(self):
        make_chat(self.tmpdir)
        path = Path(self.tmpdir) / "chat_ecdh.pem"
        self.assertTrue(path.exists())
        self.assertIn(b"BEGIN PRIVATE KEY", path.read_bytes())

    def test_ecdh_key_stable_across_instances(self):
        c1 = make_chat(self.tmpdir)
        pem1 = c1.public_pem
        c2 = make_chat(self.tmpdir)
        pem2 = c2.public_pem
        self.assertEqual(pem1, pem2)

    def test_ecdh_key_different_per_directory(self):
        tmp1 = tempfile.mkdtemp()
        tmp2 = tempfile.mkdtemp()
        c1 = make_chat(tmp1)
        c2 = make_chat(tmp2)
        self.assertNotEqual(c1.public_pem, c2.public_pem)


class TestSessionPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _inject_session(self, chat, peer_id="peerB"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = os.urandom(32)
        now = time.time()
        chat._session_keys[peer_id] = key
        chat._session_meta[peer_id] = {"created": now, "expires": now + 3600}
        chat._save_sessions()
        return key

    def test_sessions_saved_to_disk(self):
        chat = make_chat(self.tmpdir)
        self._inject_session(chat)
        path = Path(self.tmpdir) / "chat_sessions.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("peerB", data)
        self.assertIn("key", data["peerB"])
        self.assertIn("expires", data["peerB"])

    def test_sessions_loaded_on_startup(self):
        c1 = make_chat(self.tmpdir)
        key = self._inject_session(c1)
        c2 = make_chat(self.tmpdir)
        self.assertIn("peerB", c2._session_keys)
        self.assertEqual(c2._session_keys["peerB"], key)

    def test_expired_session_pruned_on_load(self):
        chat = make_chat(self.tmpdir)
        peer_id = "peerB"
        key = os.urandom(32)
        chat._session_keys[peer_id] = key
        past = time.time() - 100
        chat._session_meta[peer_id] = {"created": past - 3600, "expires": past}
        chat._save_sessions()
        chat2 = make_chat(self.tmpdir)
        self.assertNotIn(peer_id, chat2._session_keys)

    def test_has_session_returns_false_after_expiry(self):
        chat = make_chat(self.tmpdir)
        key = os.urandom(32)
        chat._session_keys["peerX"] = key
        chat._session_meta["peerX"] = {"created": time.time() - 100, "expires": time.time() - 1}
        self.assertFalse(chat.has_session("peerX"))

    def test_has_session_true_for_fresh(self):
        chat = make_chat(self.tmpdir)
        key = os.urandom(32)
        chat._session_keys["peerY"] = key
        chat._session_meta["peerY"] = {"created": time.time(), "expires": time.time() + 3600}
        self.assertTrue(chat.has_session("peerY"))

    def test_session_remaining_positive(self):
        chat = make_chat(self.tmpdir)
        key = os.urandom(32)
        chat._session_keys["peerZ"] = key
        chat._session_meta["peerZ"] = {"created": time.time(), "expires": time.time() + 1800}
        remaining = chat.session_remaining("peerZ")
        self.assertGreater(remaining, 1700)
        self.assertLess(remaining, 1900)

    def test_clear_session_removes_and_persists(self):
        chat = make_chat(self.tmpdir)
        self._inject_session(chat)
        self.assertTrue(chat.clear_session("peerB"))
        chat2 = make_chat(self.tmpdir)
        self.assertNotIn("peerB", chat2._session_keys)


class TestSendWithoutHandshake(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_send_triggers_handshake_when_no_session(self):
        chat = make_chat(self.tmpdir)
        result = chat.send("peerC", "hello")
        self.assertEqual(result.get("status"), "MQTT_OFFLINE")
        self.assertFalse(chat.has_session("peerC"))

    def test_send_uses_existing_session(self):
        chat = make_chat(self.tmpdir)
        mqtt = FakeMQTT()
        mqtt.enabled = True
        chat.mqtt = mqtt
        key = os.urandom(32)
        chat._session_keys["peerD"] = key
        chat._session_meta["peerD"] = {"created": time.time(), "expires": time.time() + 3600}
        result = chat.send("peerD", "test message")
        self.assertEqual(result.get("status"), "SENT")
        self.assertEqual(len(mqtt.published), 1)
        topic, payload = mqtt.published[0]
        self.assertEqual(topic, "ohm/chat/msg/peerD")
        self.assertNotIn("test message", json.dumps(payload))


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_status_includes_session_ttl(self):
        chat = make_chat(self.tmpdir)
        s = chat.status()
        self.assertIn("session_ttl_seconds", s)
        self.assertEqual(s["session_ttl_seconds"], 3600)


if __name__ == "__main__":
    unittest.main(verbosity=2)