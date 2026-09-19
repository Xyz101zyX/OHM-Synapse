import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
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


def make_brain(tmpdir=None):
    tmpdir = tmpdir or tempfile.mkdtemp()
    cfg = ohm.OHMConfig()
    cfg.memory_cfg = dict(cfg.memory_cfg)
    cfg.memory_cfg["persistence_file"] = str(Path(tmpdir) / "mem.json")
    cfg.memory_cfg["audit_file"] = str(Path(tmpdir) / "audit.jsonl")
    cfg.memory_cfg["export_file"] = str(Path(tmpdir) / "export.json")
    cfg.distributed_cfg = dict(cfg.distributed_cfg)
    cfg.distributed_cfg["enabled"] = False
    b = ohm.OHMSynapse(config=cfg)
    b.llm = None
    b.external_lookup_enabled = False
    return b


class TestThresholdDefaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.brain = make_brain(self.tmp)

    def tearDown(self):
        self.brain.shutdown()

    def test_default_grounding(self):
        self.assertAlmostEqual(self.brain.grounding_threshold, 0.20, places=4)

    def test_default_respond(self):
        self.assertAlmostEqual(self.brain.confidence.t_respond, 0.80, places=4)

    def test_default_caution(self):
        self.assertAlmostEqual(self.brain.confidence.t_caution, 0.50, places=4)

    def test_thresholds_dict_has_all_keys(self):
        for k in ("grounding", "confidence_respond", "confidence_caution"):
            self.assertIn(k, self.brain.thresholds)


class TestThresholdCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.brain = make_brain(self.tmp)

    def tearDown(self):
        self.brain.shutdown()

    def test_show(self):
        r = self.brain.think("/threshold")
        self.assertEqual(r.status, "THRESHOLD")
        self.assertIn("grounding", r.text)

    def test_set_grounding(self):
        r = self.brain.think("/threshold grounding 0.5")
        self.assertEqual(r.status, "THRESHOLD_SET")
        self.assertAlmostEqual(self.brain.grounding_threshold, 0.5, places=4)

    def test_set_respond(self):
        r = self.brain.think("/threshold confidence_respond 0.9")
        self.assertEqual(r.status, "THRESHOLD_SET")
        self.assertAlmostEqual(self.brain.confidence.t_respond, 0.9, places=4)

    def test_set_caution(self):
        r = self.brain.think("/threshold confidence_caution 0.4")
        self.assertEqual(r.status, "THRESHOLD_SET")
        self.assertAlmostEqual(self.brain.confidence.t_caution, 0.4, places=4)

    def test_set_invalid_range_high(self):
        r = self.brain.think("/threshold grounding 1.5")
        self.assertEqual(r.status, "THRESHOLD_ERROR")

    def test_set_invalid_range_negative(self):
        r = self.brain.think("/threshold grounding -0.1")
        self.assertEqual(r.status, "THRESHOLD_ERROR")

    def test_set_unknown_key(self):
        r = self.brain.think("/threshold nonsense 0.5")
        self.assertEqual(r.status, "THRESHOLD_ERROR")

    def test_set_missing_value(self):
        r = self.brain.think("/threshold grounding")
        self.assertEqual(r.status, "USAGE")

    def test_set_invalid_value_non_number(self):
        r = self.brain.think("/threshold grounding abc")
        self.assertEqual(r.status, "THRESHOLD_ERROR")

    def test_invariant_caution_le_respond(self):
        r = self.brain.think("/threshold confidence_caution 0.9")
        self.assertEqual(r.status, "THRESHOLD_ERROR")
        self.assertLessEqual(self.brain.confidence.t_caution, self.brain.confidence.t_respond)

    def test_invariant_respond_ge_caution(self):
        r = self.brain.think("/threshold confidence_caution 0.3")
        self.assertEqual(r.status, "THRESHOLD_SET")
        r2 = self.brain.think("/threshold confidence_respond 0.2")
        self.assertEqual(r2.status, "THRESHOLD_ERROR")


class TestThresholdReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.brain = make_brain(self.tmp)

    def tearDown(self):
        self.brain.shutdown()

    def test_reset_all(self):
        self.brain.think("/threshold grounding 0.5")
        self.brain.think("/threshold confidence_respond 0.9")
        r = self.brain.think("/threshold reset")
        self.assertEqual(r.status, "THRESHOLD_RESET")
        self.assertAlmostEqual(self.brain.grounding_threshold, 0.20, places=4)
        self.assertAlmostEqual(self.brain.confidence.t_respond, 0.80, places=4)

    def test_reset_single(self):
        self.brain.think("/threshold grounding 0.5")
        self.brain.think("/threshold confidence_respond 0.9")
        r = self.brain.think("/threshold reset grounding")
        self.assertEqual(r.status, "THRESHOLD_RESET")
        self.assertAlmostEqual(self.brain.grounding_threshold, 0.20, places=4)
        self.assertAlmostEqual(self.brain.confidence.t_respond, 0.9, places=4)


class TestThresholdPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_persist_across_restart(self):
        b1 = make_brain(self.tmp)
        b1.think("/threshold grounding 0.35")
        b1.shutdown()

        b2 = make_brain(self.tmp)
        try:
            self.assertAlmostEqual(b2.grounding_threshold, 0.35, places=4)
        finally:
            b2.shutdown()

    def test_persist_file_created(self):
        b = make_brain(self.tmp)
        b.think("/threshold grounding 0.30")
        path = Path(self.tmp) / "thresholds.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertAlmostEqual(data["grounding"], 0.30, places=4)
        b.shutdown()


class TestThresholdAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.brain = make_brain(self.tmp)

    def tearDown(self):
        self.brain.shutdown()

    def test_audit_logged(self):
        self.brain.think("/threshold grounding 0.42")
        entries = self.brain.audit_log.tail(20)
        found = [e for e in entries if e.get("event") == "threshold_changed"
                 and e.get("key") == "grounding"]
        self.assertTrue(found)
        self.assertAlmostEqual(found[-1]["new"], 0.42, places=4)


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.brain = make_brain(self.tmp)

    def tearDown(self):
        self.brain.shutdown()

    def test_high_grounding_forces_abstain(self):
        self.brain.think("/remember my cat name is Zeca")
        self.brain.think("/threshold grounding 0.99")
        r = self.brain.think("what is my cat name")
        self.assertIn(r.status, ("ABSTAIN", "CAUTION"))

    def test_low_grounding_accepts(self):
        self.brain.think("/remember my cat name is Zeca")
        self.brain.think("/threshold grounding 0.05")
        r = self.brain.think("what is my cat name")
        self.assertNotEqual(r.status, "ABSTAIN")


if __name__ == "__main__":
    unittest.main(verbosity=2)