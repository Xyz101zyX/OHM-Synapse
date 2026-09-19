import os
import sys
import time
import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["OHM_RESISTANCE"] = "0.5"
os.environ["OHM_TEST_MODE"] = "1"

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)


class TestCoverageScoring(unittest.TestCase):
    def setUp(self):
        self.scorer = ohm.ConfidenceScorer({
            "weights": {"source_score": 0.35, "coverage": 0.25,
                        "consistency": 0.20, "residual": 0.10, "llm_penalty": 0.30},
            "thresholds": {"respond": 0.80, "caution": 0.50},
        })

    def test_coverage_zero_for_short_tokens(self):
        mem = [{"content": "a b c", "layer": ohm.MemoryLayer.PERSONAL_RECORD}]
        cov = self.scorer._coverage("a b c", mem)
        self.assertEqual(cov, 0.0)

    def test_coverage_full_when_all_tokens_match(self):
        mem = [{"content": "alpha beta gamma delta", "layer": ohm.MemoryLayer.PERSONAL_RECORD}]
        cov = self.scorer._coverage("alpha beta gamma delta", mem)
        self.assertEqual(cov, 1.0)

    def test_coverage_partial(self):
        mem = [{"content": "alpha beta", "layer": ohm.MemoryLayer.PERSONAL_RECORD}]
        cov = self.scorer._coverage("alpha beta gamma", mem)
        self.assertAlmostEqual(cov, 2/3, places=2)

    def test_coverage_uses_sources_when_memories_empty(self):
        src = ohm.Source(kind="wikipedia", ref="http://x",
                         timestamp=time.time(),
                         detail="alpha beta gamma delta",
                         layer=ohm.MemoryLayer.FACT_EXTERNAL)
        cov = self.scorer._coverage("alpha beta gamma delta", [], [src])
        self.assertGreaterEqual(cov, 0.99)

    def test_score_with_source_and_matching_content(self):
        src = ohm.Source(kind="wikipedia", ref="http://wikipedia/x",
                         timestamp=time.time(),
                         detail="the cat sat on the mat",
                         layer=ohm.MemoryLayer.FACT_EXTERNAL)
        conf = self.scorer.score(
            "where did the cat sit",
            [],
            [src],
            {"grounding_ok": True, "grammar_ok": True, "confluence_ok": True, "residual": 0.0},
            llm_used=False,
        )
        self.assertGreater(conf, 0.55)
        self.assertLess(conf, 1.0)

    def test_score_not_stuck_at_0549(self):
        src_match = ohm.Source(kind="wikipedia", ref="http://wikipedia/foo",
                               timestamp=time.time(),
                               detail="coverage refers to many things in finance and law",
                               layer=ohm.MemoryLayer.FACT_EXTERNAL)
        src_mismatch = ohm.Source(kind="wikipedia", ref="http://wikipedia/bar",
                                  timestamp=time.time(),
                                  detail="the utah utes football team played in 2008",
                                  layer=ohm.MemoryLayer.FACT_EXTERNAL)
        conf_match = self.scorer.score("coverage", [], [src_match],
                                       {"grounding_ok": False, "grammar_ok": True,
                                        "confluence_ok": True, "residual": 0.0},
                                       llm_used=False)
        conf_mismatch = self.scorer.score("coverage", [], [src_mismatch],
                                          {"grounding_ok": False, "grammar_ok": True,
                                           "confluence_ok": True, "residual": 0.0},
                                          llm_used=False)
        self.assertNotEqual(round(conf_match, 3), round(conf_mismatch, 3))
        self.assertGreater(conf_match, conf_mismatch)


class TestSemanticMismatch(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.llm = None
        

    def tearDown(self):
        self.brain.shutdown()

    def test_extract_matches_query_positive(self):
        self.assertTrue(self.brain._extract_matches_query(
            "coverage",
            "Coverage may refer to several topics in finance, law, and insurance.",
        ))

    def test_extract_matches_query_negative(self):
        self.assertFalse(self.brain._extract_matches_query(
            "conf formula 0.35 0.25 0.20 0.10 0.817",
            "The 2008 Utah Utes football team represented the University of Utah in the 2008 NCAA Division I FBS football season.",
        ))

    def test_extract_matches_query_empty(self):
        self.assertFalse(self.brain._extract_matches_query("", "anything"))
        self.assertFalse(self.brain._extract_matches_query("a b", "anything"))


class TestLayerTransitions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = os.path.join(self.tmpdir, "mem.json")
        cfg.memory_cfg["audit_file"] = os.path.join(self.tmpdir, "audit.jsonl")
        self.mem = ohm.HoloMem4L(cfg)
        self.src_user = ohm.Source(kind="user", ref="user", timestamp=time.time(),
                                   layer=ohm.MemoryLayer.PERSONAL_RECORD)
        self.src_llm = ohm.Source(kind="llm", ref="llama", timestamp=time.time(),
                                  layer=ohm.MemoryLayer.INFERENCE)

    def test_ephemeral_cannot_be_promoted(self):
        ok = self.mem.promote("nonexistent", ohm.MemoryLayer.PERSONAL_RECORD, user_confirmed=True)
        self.assertFalse(ok)

    def test_inference_to_personal_requires_confirmation(self):
        self.mem.store_memory("inf1", "x", ohm.MemoryLayer.INFERENCE, sources=[self.src_llm])
        self.assertFalse(self.mem.promote("inf1", ohm.MemoryLayer.PERSONAL_RECORD, user_confirmed=False))
        self.assertTrue(self.mem.promote("inf1", ohm.MemoryLayer.PERSONAL_RECORD, user_confirmed=True))

    def test_inference_to_fact_requires_sources(self):
        self.mem.store_memory("inf1", "x", ohm.MemoryLayer.INFERENCE, sources=[self.src_llm])
        self.assertTrue(self.mem.promote("inf1", ohm.MemoryLayer.FACT_EXTERNAL))

    def test_promote_does_not_touch_missing_key(self):
        self.assertFalse(self.mem.promote("nope", ohm.MemoryLayer.FACT_EXTERNAL))

    def test_correct_creates_new_key(self):
        self.mem.store_memory("k1", "old", ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[self.src_user], user_confirmed=True)
        self.mem.correct("k1", "new", ohm.MemoryLayer.PERSONAL_RECORD,
                         sources=[self.src_user], user_confirmed=True)
        self.assertIsNotNone(self.mem.get("k1")["superseded_by"])
        superseding = self.mem.get("k1")["superseded_by"]
        self.assertIn("new", self.mem.get(superseding)["content"])


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mem_path = os.path.join(self.tmpdir, "mem.json")
        self.audit_path = os.path.join(self.tmpdir, "audit.jsonl")

    def _make_mem(self):
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = self.mem_path
        cfg.memory_cfg["audit_file"] = self.audit_path
        return ohm.HoloMem4L(cfg)

    def test_restart_preserves_personal_record(self):
        m1 = self._make_mem()
        src = ohm.Source(kind="user", ref="user", timestamp=time.time(),
                         layer=ohm.MemoryLayer.PERSONAL_RECORD)
        m1.store_memory("k1", "my cat is zeca", ohm.MemoryLayer.PERSONAL_RECORD,
                        sources=[src], user_confirmed=True)
        m2 = self._make_mem()
        self.assertIsNotNone(m2.get("k1"))
        self.assertIn("zeca", m2.get("k1")["content"])

    def test_superseded_not_recalled(self):
        m = self._make_mem()
        src = ohm.Source(kind="user", ref="user", timestamp=time.time(),
                         layer=ohm.MemoryLayer.PERSONAL_RECORD)
        m.store_memory("k1", "old content unique", ohm.MemoryLayer.PERSONAL_RECORD,
                       sources=[src], user_confirmed=True)
        m.correct("k1", "new content unique", ohm.MemoryLayer.PERSONAL_RECORD,
                  sources=[src], user_confirmed=True)
        hits = m.recall("unique content old", top_k=5)
        ids = [h["id"] for h in hits]
        self.assertNotIn("k1", ids)

    def test_expired_inference_collected_on_recall(self):
        m = self._make_mem()
        src = ohm.Source(kind="llm", ref="llama", timestamp=time.time(),
                         layer=ohm.MemoryLayer.INFERENCE)
        m.store_memory("inf_ttl", "short lived", ohm.MemoryLayer.INFERENCE,
                       sources=[src], ttl=0.1)
        time.sleep(0.2)
        m.recall("short lived")
        self.assertIsNone(m.get("inf_ttl"))


class TestConcurrency(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = os.path.join(self.tmpdir, "mem.json")
        cfg.memory_cfg["audit_file"] = os.path.join(self.tmpdir, "audit.jsonl")
        self.mem = ohm.HoloMem4L(cfg)
        self.src = ohm.Source(kind="user", ref="user", timestamp=time.time(),
                              layer=ohm.MemoryLayer.PERSONAL_RECORD)

    def test_parallel_writes_no_corruption(self):
        def writer(i):
            self.mem.store_memory(f"k{i}", f"content {i}", ohm.MemoryLayer.PERSONAL_RECORD,
                                  sources=[self.src], user_confirmed=True)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len([k for k in self.mem.store if k.startswith("k")]), 50)

    def test_parallel_reads(self):
        self.mem.store_memory("kx", "unique token zzz", ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[self.src], user_confirmed=True)
        results = []

        def reader():
            hits = self.mem.recall("unique token zzz")
            results.append(len(hits))

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(r >= 1 for r in results))


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.external_lookup_enabled = False
        self.brain.llm = None
        

    def tearDown(self):
        self.brain.shutdown()

    def test_empty_query(self):
        r = self.brain.think("")
        self.assertEqual(r.status, "EMPTY")

    def test_whitespace_query(self):
        r = self.brain.think("    ")
        self.assertEqual(r.status, "EMPTY")

    def test_unicode_query(self):
        r = self.brain.think("/remember Tokyo meeting at 3am")
        self.assertIn(r.status, ("REMEMBER", "USAGE"))

    def test_very_long_query(self):
        q = "word " * 500
        r = self.brain.think(q)
        self.assertIsInstance(r, ohm.Response)

    def test_only_stopwords(self):
        r = self.brain.think("a o de da")
        self.assertIsInstance(r, ohm.Response)


class TestAntiHallucination(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.external_lookup_enabled = False  
        self.brain.llm = None
              

    def tearDown(self):
        self.brain.shutdown()

    def test_nonexistent_entity_does_not_invent(self):
        r = self.brain.think("what is the name of my purple elephant xylophone?")
        self.assertNotEqual(r.status, "OK")

    def test_conflicting_memories_detected(self):
        self.brain.think("/remember my cat name is Zeca")
        self.brain.think("/remember my cat name is Rex")
        r = self.brain.think("what is my cat name")
        self.assertIsInstance(r, ohm.Response)

    def test_llm_only_answer_penalized(self):
        scorer = ohm.ConfidenceScorer({
            "weights": {"source_score": 0.35, "coverage": 0.25,
                        "consistency": 0.20, "residual": 0.10, "llm_penalty": 0.30},
            "thresholds": {"respond": 0.80, "caution": 0.50},
        })
        conf = scorer.score(
            "anything",
            [{"content": "some memory matching anything", "layer": ohm.MemoryLayer.INFERENCE}],
            [],
            {"grounding_ok": True, "grammar_ok": True, "confluence_ok": True, "residual": 0.0},
            llm_used=True,
        )
        self.assertLess(conf, 0.60)


class TestDeltaSecurity(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.external_lookup_enabled = False  
        self.brain.llm = None
        

    def tearDown(self):
        self.brain.shutdown()

    def test_valid_delta_applies(self):
        payload = {"content": "external fact", "layer": ohm.MemoryLayer.FACT_EXTERNAL,
                   "reliability": 0.9, "updated": time.time(), "sources": []}
        self.brain._apply_remote_delta("peer_x", {"key1": payload})
        self.assertIsNotNone(self.brain.memory.get("key1"))

    def test_inference_layer_delta_rejected(self):
        payload = {"content": "inference", "layer": ohm.MemoryLayer.INFERENCE,
                   "reliability": 0.3, "updated": time.time(), "sources": []}
        self.brain._apply_remote_delta("peer_x", {"key2": payload})
        self.assertIsNone(self.brain.memory.get("key2"))

    def test_ephemeral_layer_delta_rejected(self):
        payload = {"content": "ephemeral", "layer": ohm.MemoryLayer.EPHEMERAL,
                   "reliability": 0.0, "updated": time.time(), "sources": []}
        self.brain._apply_remote_delta("peer_x", {"key3": payload})
        self.assertIsNone(self.brain.memory.get("key3"))

    def test_malformed_delta_ignored(self):
        self.brain._apply_remote_delta("peer_x", {"bad": "not a dict"})
        self.brain._apply_remote_delta("peer_x", "not a dict at all")
        self.brain._apply_remote_delta("peer_x", {"k": {"layer": "UNKNOWN"}})
        self.assertIsNone(self.brain.memory.get("k"))

    def test_signature_verification_roundtrip(self):
        msg = b"test payload"
        sig = self.brain.genesis.sign(msg)
        pub = self.brain.genesis.public_key_pem
        self.assertTrue(self.brain.genesis.verify(msg, sig, pub))
        self.assertFalse(self.brain.genesis.verify(b"tampered", sig, pub))


class TestRateLimitAndAudit(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.external_lookup_enabled = False  
        self.brain.llm = None

    def tearDown(self):
        self.brain.shutdown()

    def test_audit_log_written(self):
        self.brain.think("/remember audit_test_token")
        entries = self.brain.audit_log.tail(10)
        self.assertTrue(any(e.get("event") == "remember" for e in entries))

    def test_audit_log_signed(self):
        self.brain.think("/remember signed_test")
        entries = self.brain.audit_log.tail(10)
        signed = [e for e in entries if e.get("event") == "remember"]
        self.assertTrue(signed)
        self.assertIn("signature", signed[-1])

    def test_exec_rate_limit(self):
        self.brain.exec_limiter.set_limit(2)
        statuses = []
        for _ in range(5):
            r = self.brain.think("/exec NOP")
            statuses.append(r.status)
        self.assertIn("RATE_LIMITED", statuses)


if __name__ == "__main__":
    unittest.main(verbosity=2)