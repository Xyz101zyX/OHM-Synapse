import os
os.environ["OHM_TEST_MODE"] = "1"
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

from ohm_kairos import KairosEngine, humanize_delta, humanize_ts, Event, Episode, Deadline


def make_engine():
    tmp = Path(tempfile.mkdtemp())
    return KairosEngine({"episode_gap_seconds": 2, "half_life_seconds": 60, "recall_boost": 0.5}, tmp)


class TestEventLog(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()

    def test_log_event_creates_record(self):
        e = self.engine.log_event("query", "hello world", ref="user")
        self.assertEqual(e.kind, "query")
        self.assertIn("hello", e.summary)
        self.assertEqual(len(self.engine.events), 1)

    def test_events_persist_across_instances(self):
        self.engine.log_event("memory", "saved fact")
        data_dir = self.engine.data_dir
        engine2 = KairosEngine({}, data_dir)
        self.assertEqual(len(engine2.events), 1)

    def test_profile_updates_on_event(self):
        self.engine.log_event("query", "a")
        self.engine.log_event("query", "b")
        self.assertEqual(self.engine.profile["total_events"], 2)
        self.assertIsNotNone(self.engine.profile["first_event"])


class TestTimeline(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()

    def test_timeline_returns_recent(self):
        self.engine.log_event("query", "old event")
        time.sleep(0.1)
        self.engine.log_event("query", "recent event")
        events = self.engine.timeline(start=time.time() - 10, limit=10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].summary, "recent event")

    def test_timeline_kind_filter(self):
        self.engine.log_event("query", "one")
        self.engine.log_event("memory", "two")
        self.engine.log_event("chat_in", "three")
        queries = self.engine.timeline(kinds=("query",), limit=10)
        self.assertEqual(len(queries), 1)

    def test_events_mentioning(self):
        self.engine.log_event("query", "tell me about python")
        self.engine.log_event("query", "what about javascript")
        hits = self.engine.events_mentioning("python")
        self.assertEqual(len(hits), 1)

    def test_since_last(self):
        self.engine.log_event("query", "topic x discussion")
        delta = self.engine.since_last("topic x")
        self.assertIsNotNone(delta)
        self.assertLess(delta, 1.0)

    def test_since_last_missing(self):
        delta = self.engine.since_last("nonexistent-topic")
        self.assertIsNone(delta)


class TestEpisodes(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()

    def test_same_episode_for_close_events(self):
        self.engine.log_event("query", "a")
        self.engine.log_event("query", "b")
        episodes = list(self.engine.episodes.values())
        self.assertEqual(len(episodes), 1)
        self.assertEqual(len(episodes[0].events), 2)

    def test_new_episode_after_gap(self):
        self.engine.log_event("query", "a")
        time.sleep(2.5)
        self.engine.log_event("query", "b")
        episodes = list(self.engine.episodes.values())
        self.assertGreaterEqual(len(episodes), 2)


class TestTemporalScore(unittest.TestCase):
    def test_recent_boosts_more(self):
        engine = make_engine()
        now = time.time()
        s_new = engine.temporal_score(now, now)
        s_old = engine.temporal_score(now - 30, now)
        self.assertGreater(s_new, s_old)
        self.assertGreater(s_new, 1.0)
        self.assertGreater(s_old, 1.0)

    def test_decay_approaches_one(self):
        engine = make_engine()
        now = time.time()
        s_very_old = engine.temporal_score(now - 86400 * 100, now)
        self.assertAlmostEqual(s_very_old, 1.0, places=3)


class TestDeadlines(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()

    def test_add_deadline(self):
        d = self.engine.add_deadline(time.time() + 3600, "submit report")
        self.assertFalse(d.done)
        self.assertEqual(len(self.engine.list_deadlines()), 1)

    def test_complete_deadline(self):
        d = self.engine.add_deadline(time.time() + 3600, "call mom")
        ok = self.engine.complete_deadline(d.id)
        self.assertTrue(ok)
        self.assertEqual(len(self.engine.list_deadlines()), 0)
        self.assertEqual(len(self.engine.list_deadlines(only_pending=False)), 1)

    def test_complete_missing(self):
        self.assertFalse(self.engine.complete_deadline("nonexistent"))


class TestCircadian(unittest.TestCase):
    def test_circadian_summary(self):
        engine = make_engine()
        for _ in range(3):
            engine.log_event("query", "x")
        summary = engine.circadian_summary()
        self.assertEqual(summary["total_events"], 3)
        self.assertEqual(len(summary["peak_hours"]), 3)
        self.assertEqual(len(summary["hourly_distribution"]), 24)


class TestHelpers(unittest.TestCase):
    def test_humanize_delta_seconds(self):
        self.assertEqual(humanize_delta(45), "45s")

    def test_humanize_delta_minutes(self):
        self.assertEqual(humanize_delta(300), "5min")

    def test_humanize_delta_hours(self):
        self.assertIn("h", humanize_delta(7200))

    def test_humanize_delta_days(self):
        self.assertIn("d", humanize_delta(200000))

    def test_humanize_ts(self):
        ts = humanize_ts(time.time())
        self.assertRegex(ts, r"\d{4}-\d{2}-\d{2}")


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.llm = None
        self.brain.external_lookup_enabled = False

    def tearDown(self):
        self.brain.shutdown()

    def test_query_logged_in_kairos(self):
        before = len(self.brain.kairos.events)
        self.brain.think("hello test")
        after = len(self.brain.kairos.events)
        self.assertGreater(after, before)

    def test_kairo_command(self):
        r = self.brain.think("/kairo")
        self.assertEqual(r.status, "KAIRO")

    def test_timeline_command(self):
        self.brain.think("test query for timeline")
        r = self.brain.think("/timeline")
        self.assertEqual(r.status, "TIMELINE")

    def test_when_command(self):
        self.brain.think("unique topic zyxw")
        r = self.brain.think("/when zyxw")
        self.assertEqual(r.status, "WHEN")

    def test_since_command(self):
        self.brain.think("unique topic abcdef")
        r = self.brain.think("/since abcdef")
        self.assertEqual(r.status, "SINCE")

    def test_deadline_add_list_done(self):
        r1 = self.brain.think("/deadline add 3600 finish report")
        self.assertEqual(r1.status, "DEADLINE_ADD")
        did = r1.text.split("[")[1].split("]")[0]
        r2 = self.brain.think("/deadline")
        self.assertEqual(r2.status, "DEADLINE")
        self.assertIn("finish report", r2.text)
        r3 = self.brain.think(f"/deadline done {did}")
        self.assertEqual(r3.status, "DEADLINE_DONE")

    def test_episodes_command(self):
        self.brain.think("first message")
        self.brain.think("second message")
        r = self.brain.think("/episodes")
        self.assertEqual(r.status, "EPISODES")

    def test_circadian_command(self):
        self.brain.think("activity test")
        r = self.brain.think("/circadian")
        self.assertEqual(r.status, "CIRCADIAN")

    def test_today_command(self):
        self.brain.think("something today")
        r = self.brain.think("/today")
        self.assertIn(r.status, ("TODAY", "TODAY"))

    def test_yesterday_command(self):
        r = self.brain.think("/yesterday")
        self.assertIn(r.status, ("YESTERDAY", "YESTERDAY"))

    def test_recall_boosted_by_recency(self):
        self.brain.think("/remember alpha beta gamma")
        hits = self.brain._stage1_recall("alpha beta")
        self.assertTrue(any("alpha" in h.get("content", "") for h in hits))
        self.assertTrue(all("temporal_score" in h for h in hits))


if __name__ == "__main__":
    unittest.main(verbosity=2)