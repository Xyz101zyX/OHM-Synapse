import os
import sys
import time
import json
import tempfile
import unittest
from pathlib import Path

os.environ["OHM_RESISTANCE"] = "0.5"
os.environ["OHM_TEST_MODE"] = "1"

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

if not MAIN.exists():
    raise FileNotFoundError(f"ohm_synapse.py not found next to test file: {MAIN}")

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


class TestMemoryLayers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = os.path.join(self.tmpdir, "mem.json")
        cfg.memory_cfg["audit_file"] = os.path.join(self.tmpdir, "audit.jsonl")
        self.mem = ohm.HoloMem4L(cfg)

    def test_fact_external_requires_source(self):
        ok = self.mem.store_memory("k1", "x", ohm.MemoryLayer.FACT_EXTERNAL, sources=[])
        self.assertFalse(ok)

    def test_fact_external_with_source_ok(self):
        src = ohm.Source(kind="wikipedia", ref="http://x", timestamp=time.time())
        ok = self.mem.store_memory("k1", "x", ohm.MemoryLayer.FACT_EXTERNAL, sources=[src])
        self.assertTrue(ok)

    def test_personal_record_requires_confirmation(self):
        ok = self.mem.store_memory("k1", "x", ohm.MemoryLayer.PERSONAL_RECORD,
                                   sources=[ohm.Source(kind="user", ref="u", timestamp=time.time())],
                                   user_confirmed=False)
        self.assertFalse(ok)
        ok2 = self.mem.store_memory("k2", "x", ohm.MemoryLayer.PERSONAL_RECORD,
                                    sources=[ohm.Source(kind="user", ref="u", timestamp=time.time())],
                                    user_confirmed=True)
        self.assertTrue(ok2)

    def test_ephemeral_never_persists(self):
        ok = self.mem.store_memory("k1", "x", ohm.MemoryLayer.EPHEMERAL)
        self.assertFalse(ok)

    def test_inference_has_ttl(self):
        src = ohm.Source(kind="llm", ref="llama", timestamp=time.time())
        ok = self.mem.store_memory("k1", "x", ohm.MemoryLayer.INFERENCE,
                                   sources=[src], ttl=1.0)
        self.assertTrue(ok)
        self.assertIsNotNone(self.mem.get("k1")["expires"])

    def test_forget(self):
        src = ohm.Source(kind="user", ref="u", timestamp=time.time())
        self.mem.store_memory("k1", "x", ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[src], user_confirmed=True)
        self.assertTrue(self.mem.forget("k1"))
        self.assertIsNone(self.mem.get("k1"))

    def test_correct_supersedes(self):
        src = ohm.Source(kind="user", ref="u", timestamp=time.time())
        self.mem.store_memory("k1", "old", ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[src], user_confirmed=True)
        self.mem.correct("k1", "new", ohm.MemoryLayer.PERSONAL_RECORD,
                         sources=[src], user_confirmed=True)
        self.assertIsNotNone(self.mem.get("k1")["superseded_by"])

    def test_export_contains_all(self):
        src = ohm.Source(kind="user", ref="u", timestamp=time.time())
        self.mem.store_memory("k1", "x", ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[src], user_confirmed=True)
        dump = self.mem.export()
        self.assertIn("k1", dump)


class TestGrammar(unittest.TestCase):
    def setUp(self):
        self.g = ohm.StructuralGrammar()

    def test_fact_requires_source_url(self):
        ok, _ = self.g.validate({"type": "Fact", "statement": "x"})
        self.assertFalse(ok)
        ok, _ = self.g.validate({"type": "Fact", "statement": "x",
                                 "source_url": "http://x", "source_kind": "wikipedia"})
        self.assertTrue(ok)

    def test_personal_note_requires_confirmation(self):
        ok, _ = self.g.validate({"type": "PersonalNote", "statement": "x",
                                 "user_confirmed": False})
        self.assertFalse(ok)
        ok, _ = self.g.validate({"type": "PersonalNote", "statement": "x",
                                 "user_confirmed": True})
        self.assertTrue(ok)

    def test_inference_requires_derivation(self):
        ok, _ = self.g.validate({"type": "Inference", "statement": "x"})
        self.assertFalse(ok)
        ok, _ = self.g.validate({"type": "Inference", "statement": "x",
                                 "derived_from": ["llm"]})
        self.assertTrue(ok)


class TestConfidenceScorer(unittest.TestCase):
    def setUp(self):
        cfg = ohm.OHMConfig()
        self.scorer = ohm.ConfidenceScorer(cfg.confidence_cfg)

    def test_personal_record_high_confidence(self):
        src = ohm.Source(kind="user", ref="u", timestamp=time.time(),
                         layer=ohm.MemoryLayer.PERSONAL_RECORD)
        conf = self.scorer.score(
            "what is my cat name",
            [{"content": "my cat name is zeca", "layer": ohm.MemoryLayer.PERSONAL_RECORD}],
            [src],
            {"grounding_ok": True, "grammar_ok": True,
             "confluence_ok": True, "residual": 0.0},
            llm_used=False,
        )
        self.assertGreaterEqual(conf, 0.80)

    def test_llm_alone_abstains(self):
        conf = self.scorer.score("q", [], [],
                                 {"grounding_ok": False, "grammar_ok": False,
                                  "confluence_ok": True, "residual": 0.15},
                                 llm_used=True)
        self.assertLess(conf, 0.50)

    def test_decision_thresholds(self):
        self.assertEqual(self.scorer.decision(0.85), "respond")
        self.assertEqual(self.scorer.decision(0.65), "caution")
        self.assertEqual(self.scorer.decision(0.30), "abstain")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = __import__("os").path.join(self._tmpdir, "mem.json")
        cfg.memory_cfg["audit_file"] = __import__("os").path.join(self._tmpdir, "audit.jsonl")
        cfg.memory_cfg["export_file"] = __import__("os").path.join(self._tmpdir, "export.json")
        self.brain = ohm.OHMSynapse(config=cfg)
        self.brain.config.llm_cfg["enabled"] = False
        self.brain.llm = None
        self.brain.external_lookup_enabled = False

    def tearDown(self):
        self.brain.shutdown()

    def test_abstain_on_empty_knowledge(self):
        r = self.brain.think("what is the name of my fish?")
        self.assertIn(r.status, ("ABSTAIN", "CAUTION", "OK"))

    def test_remember_then_recall(self):
        self.brain.think("/remember my cat is named Zeca")
        r = self.brain.think("what is the name of my cat?")
        self.assertNotEqual(r.status, "ABSTAIN")

    def test_audit_lists_memory(self):
        self.brain.think("/remember teste_audit_xyz")
        r = self.brain.think("/audit")
        self.assertEqual(r.status, "AUDIT")
        self.assertIn("teste_audit_xyz", r.text)

    def test_forget_removes(self):
        self.brain.think("/remember para_esquecer")
        entries = self.brain.memory.audit("para_esquecer")
        self.assertGreater(len(entries), 0)
        key = entries[0]["id"]
        r = self.brain.think(f"/forget {key}")
        self.assertEqual(r.status, "FORGET")
        self.assertIsNone(self.brain.memory.get(key))

    def test_correct_supersedes(self):
        self.brain.think("/remember versao_antiga")
        entries = self.brain.memory.audit("versao_antiga")
        key = entries[0]["id"]
        r = self.brain.think(f"/correct {key} versao_nova")
        self.assertEqual(r.status, "CORRECT")
        self.assertIsNotNone(self.brain.memory.get(key)["superseded_by"])

    def test_export_creates_file(self):
        self.brain.think("/remember export_test")
        r = self.brain.think("/export")
        self.assertEqual(r.status, "EXPORT")

    def test_citation_format_always_has_sources_section(self):
        r = self.brain.think("hi")
        formatted = ohm.CitationFormatter.format(r)
        self.assertIn("RESPONSE", formatted)
        self.assertIn("SOURCES", formatted)
        self.assertIn("CONFIDENCE", formatted)

    def test_rate_limit(self):
        self.brain.query_limiter.set_limit(3)
        results = [self.brain.think(f"q{i}") for i in range(10)]
        limited = [r for r in results if r.status == "RATE_LIMITED"]
        self.assertGreaterEqual(len(limited), 5)
        self.assertEqual(results[0].status, "ABSTAIN")

    def test_help_command(self):
        r = self.brain.think("/help")
        self.assertEqual(r.status, "HELP")


class TestSecurity(unittest.TestCase):
    def test_public_broker_rejected(self):
        q = __import__("queue").Queue()
        client = ohm.MQTTClient("broker.hivemq.com", 8883, "test", q,
                                {"allow_public_broker": False, "require_tls": True})
        self.assertFalse(client.enabled)

    def test_rate_limiter(self):
        rl = ohm.RateLimiter(max_per_minute=2)
        self.assertTrue(rl.allow("x"))
        self.assertTrue(rl.allow("x"))
        self.assertFalse(rl.allow("x"))

    def test_sandbox_blocks_remote_exec(self):
        ohm.SandboxGuard.enter_remote()
        try:
            with self.assertRaises(PermissionError):
                ohm.FluxExecutor.run(b"\xC3")
        finally:
            ohm.SandboxGuard.exit_remote()


class TestGenesis(unittest.TestCase):
    def setUp(self):
        self.gen = ohm.GenesisCore("test_sig", 1)

    def test_sign_and_verify_roundtrip(self):
        msg = b"hello world"
        sig = self.gen.sign(msg)
        self.assertTrue(self.gen.verify(msg, sig, self.gen.public_key_pem))

    def test_verify_fails_on_tampered_message(self):
        msg = b"hello"
        sig = self.gen.sign(msg)
        self.assertFalse(self.gen.verify(b"hello!", sig, self.gen.public_key_pem))

    def test_node_id_stable(self):
        gen2 = ohm.GenesisCore("test_sig", 1)
        self.assertEqual(self.gen.node_id, gen2.node_id)


class TestDeterministicGenesis(unittest.TestCase):
    def test_same_seed_same_output(self):
        a = ohm.DeterministicGenesis("x", 1)
        b = ohm.DeterministicGenesis("x", 1)
        self.assertEqual(a.urandom(64), b.urandom(64))

    def test_different_seed_different_output(self):
        a = ohm.DeterministicGenesis("x", 1)
        b = ohm.DeterministicGenesis("y", 1)
        self.assertNotEqual(a.urandom(64), b.urandom(64))


class TestGreekFramework(unittest.TestCase):
    def test_psi_runs(self):
        if not ohm.HAS_NUMPY:
            self.skipTest("numpy missing")
        import numpy as np
        g = ohm.GreekFramework(alfa=[np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])],
                               beta_func=lambda x, m, s: x)
        psi = g.calculate_psi()
        self.assertIsInstance(psi, float)


class TestArchetype(unittest.TestCase):
    def test_infer_archetype_default(self):
        a = ohm.infer_archetype("random text with no keywords")
        self.assertIn(a, ohm.ARCHETYPE_LETTERS)

    def test_infer_archetype_keyword(self):
        a = ohm.infer_archetype("creativity and new beginnings")
        self.assertEqual(a, "A")


if __name__ == "__main__":
    unittest.main(verbosity=2)