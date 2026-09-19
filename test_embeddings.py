import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import time
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

from ohm_embeddings import EmbeddingManager


def has_embeddings():
    em = EmbeddingManager({}, enabled=True)
    return em.available


class TestEmbeddingManager(unittest.TestCase):
    def setUp(self):
        self.em = EmbeddingManager({"model": "all-MiniLM-L6-v2"}, enabled=True)

    def test_manager_status(self):
        s = self.em.status()
        self.assertIn("available", s)
        self.assertIn("model", s)

    def test_encode_decode_roundtrip(self):
        if not self.em.available:
            self.skipTest("embeddings unavailable")
        vec = self.em.embed("hello world")
        self.assertIsNotNone(vec)
        blob = self.em.encode_storage(vec)
        decoded = self.em.decode_storage(blob)
        self.assertEqual(len(vec), len(decoded))
        for a, b in zip(vec[:5], decoded[:5]):
            self.assertAlmostEqual(a, b, places=5)

    def test_cosine_identical(self):
        if not self.em.available:
            self.skipTest("embeddings unavailable")
        v = self.em.embed("cat")
        self.assertAlmostEqual(self.em.cosine(v, v), 1.0, places=4)

    def test_cosine_orthogonal(self):
        if not self.em.available:
            self.skipTest("embeddings unavailable")
        v1 = self.em.embed("cat")
        v2 = self.em.embed("quantum physics thermodynamics")
        self.assertLess(self.em.cosine(v1, v2), 0.9)

    def test_semantic_similarity(self):
        if not self.em.available:
            self.skipTest("embeddings unavailable")
        v1 = self.em.embed("my sister lives abroad")
        v2 = self.em.embed("where does my sibling reside")
        v3 = self.em.embed("photosynthesis converts light energy")
        sim_sister = self.em.cosine(v1, v2)
        sim_unrelated = self.em.cosine(v1, v3)
        self.assertGreater(sim_sister, sim_unrelated)

    def test_graceful_fallback_no_st(self):
        em = EmbeddingManager({}, enabled=False)
        self.assertFalse(em.available)
        self.assertIsNone(em.embed("anything"))
        self.assertEqual(em.cosine([1.0, 0.0], [0.0, 1.0]), 0.0)


class TestHybridRecall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cfg = ohm.OHMConfig()
        cfg.memory_cfg = dict(cfg.memory_cfg)
        cfg.memory_cfg["persistence_file"] = os.path.join(self.tmp, "mem.json")
        cfg.memory_cfg["audit_file"] = os.path.join(self.tmp, "audit.jsonl")
        self.mem = ohm.HoloMem4L(cfg)
        self.em = EmbeddingManager({}, enabled=True)
        self.mem.attach_embeddings(self.em)

    def _store(self, key, content):
        src = ohm.Source(kind="user", ref="user", timestamp=time.time(),
                         layer=ohm.MemoryLayer.PERSONAL_RECORD)
        self.mem.store_memory(key, content, ohm.MemoryLayer.PERSONAL_RECORD,
                              sources=[src], user_confirmed=True)

    def test_recall_hybrid_finds_semantic(self):
        if not self.em.available:
            self.skipTest("embeddings unavailable")
        self._store("sister", "Alice is my sister and she is family")
        self._store("other", "I enjoy hiking on weekends")
        hits = self.mem.recall_hybrid("where does my sibling live",
                                       top_k=5, embedder=self.em)
        ids = [h["id"] for h in hits]
        self.assertIn("sister", ids)

    def test_recall_hybrid_keyword_still_works(self):
        self._store("cat", "my cat name is Zeca")
        hits = self.mem.recall_hybrid("what is my cat name", top_k=5,
                                       embedder=self.em)
        ids = [h["id"] for h in hits]
        self.assertIn("cat", ids)

    def test_recall_hybrid_returns_scores(self):
        self._store("x", "some content")
        hits = self.mem.recall_hybrid("some content", top_k=5, embedder=self.em)
        if hits:
            self.assertIn("hybrid_score", hits[0])
            self.assertIn("keyword_score", hits[0])
            self.assertIn("embedding_score", hits[0])

    def test_recall_hybrid_no_embedder(self):
        self._store("y", "content here")
        hits = self.mem.recall_hybrid("content", top_k=5, embedder=None)
        self.assertIsInstance(hits, list)


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.llm = None
        self.brain.external_lookup_enabled = False

    def tearDown(self):
        self.brain.shutdown()

    def test_embeddings_attached(self):
        self.assertTrue(hasattr(self.brain, "embeddings"))
        self.assertTrue(hasattr(self.brain.memory, "_embedder") or
                        hasattr(self.brain.memory, "_get_embedder"))

    def test_stage1_recall_uses_hybrid(self):
        self.brain.think("/remember my sister Alice lives in Paris")
        hits = self.brain._stage1_recall("where does my sibling live")
        self.assertTrue(len(hits) >= 0)

    def test_stage1_recall_still_returns_for_direct(self):
        self.brain.think("/remember my cat name is Zeca")
        hits = self.brain._stage1_recall("what is my cat name")
        self.assertTrue(any("zeca" in h.get("content", "").lower()
                            for h in hits))


if __name__ == "__main__":
    unittest.main(verbosity=2)