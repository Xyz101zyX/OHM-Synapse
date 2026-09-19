import json
import math
import time
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import deque
from datetime import datetime


EVENT_KINDS = ("memory", "query", "chat_in", "chat_out", "decision", "milestone", "deadline")


@dataclass
class Event:
    id: str
    ts: float
    kind: str
    summary: str
    ref: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Episode:
    id: str
    started: float
    ended: Optional[float]
    label: str
    events: List[str] = field(default_factory=list)


@dataclass
class Deadline:
    id: str
    ts: float
    label: str
    done: bool = False
    created: float = 0.0


def humanize_delta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def humanize_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class KairosEngine:
    def __init__(self, config: Dict[str, Any], data_dir: Path):
        self.config = config or {}
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.events_file = self.data_dir / "kairos_events.json"
        self.episodes_file = self.data_dir / "kairos_episodes.json"
        self.deadlines_file = self.data_dir / "kairos_deadlines.json"
        self.profile_file = self.data_dir / "kairos_profile.json"

        self.events: deque = deque(maxlen=20000)
        self.episodes: Dict[str, Episode] = {}
        self.deadlines: Dict[str, Deadline] = {}
        self.profile: Dict[str, Any] = {
            "hourly_activity": [0] * 24,
            "daily_activity": [0] * 7,
            "total_events": 0,
            "first_event": None,
            "last_event": None,
        }

        self.episode_gap: float = float(self.config.get("episode_gap_seconds", 1800))
        self.half_life: float = float(self.config.get("half_life_seconds", 604800))
        self.recall_boost: float = float(self.config.get("recall_boost", 0.3))

        self._load()

    def _load(self):
        try:
            if self.events_file.exists():
                data = json.loads(self.events_file.read_text(encoding="utf-8"))
                for e in data:
                    self.events.append(Event(**e))
        except Exception:
            pass
        try:
            if self.episodes_file.exists():
                data = json.loads(self.episodes_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self.episodes[k] = Episode(**v)
        except Exception:
            pass
        try:
            if self.deadlines_file.exists():
                data = json.loads(self.deadlines_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self.deadlines[k] = Deadline(**v)
        except Exception:
            pass
        try:
            if self.profile_file.exists():
                loaded = json.loads(self.profile_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.profile.update(loaded)
        except Exception:
            pass

    def _save_events(self):
        try:
            self.events_file.write_text(
                json.dumps([asdict(e) for e in self.events], ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _save_episodes(self):
        try:
            self.episodes_file.write_text(
                json.dumps({k: asdict(v) for k, v in self.episodes.items()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _save_deadlines(self):
        try:
            self.deadlines_file.write_text(
                json.dumps({k: asdict(v) for k, v in self.deadlines.items()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _save_profile(self):
        try:
            self.profile_file.write_text(
                json.dumps(self.profile, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def _hash_id(self, *parts) -> str:
        return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:12]

    def log_event(self, kind: str, summary: str, ref: str = "",
                  meta: Optional[Dict[str, Any]] = None) -> Event:
        now = time.time()
        eid = self._hash_id(kind, ref, now, len(self.events))
        ev = Event(
            id=eid,
            ts=now,
            kind=kind,
            summary=(summary or "")[:200],
            ref=ref or "",
            meta=meta or {},
        )
        self.events.append(ev)
        self._update_profile(now)
        self._attach_to_episode(ev)
        self._save_events()
        return ev

    def _update_profile(self, ts: float):
        dt = datetime.fromtimestamp(ts)
        hours = self.profile.get("hourly_activity") or [0] * 24
        days = self.profile.get("daily_activity") or [0] * 7
        if len(hours) != 24:
            hours = [0] * 24
        if len(days) != 7:
            days = [0] * 7
        hours[dt.hour] += 1
        days[dt.weekday()] += 1
        self.profile["hourly_activity"] = hours
        self.profile["daily_activity"] = days
        self.profile["total_events"] = int(self.profile.get("total_events", 0)) + 1
        if self.profile.get("first_event") is None:
            self.profile["first_event"] = ts
        self.profile["last_event"] = ts
        self._save_profile()

    def _attach_to_episode(self, ev: Event):
        last = None
        for e in reversed(self.events):
            if e.id != ev.id:
                last = e
                break
        if last is None:
            self._start_episode(ev)
            return
        gap = ev.ts - last.ts
        if gap > self.episode_gap:
            self._close_open_episode(last.ts)
            self._start_episode(ev)
            return
        for ep in self.episodes.values():
            if ep.ended is None:
                ep.events.append(ev.id)
                self._save_episodes()
                return
        self._start_episode(ev)

    def _start_episode(self, ev: Event):
        eid = self._hash_id("episode", ev.ts)
        self.episodes[eid] = Episode(id=eid, started=ev.ts, ended=None, label="", events=[ev.id])
        self._save_episodes()

    def _close_open_episode(self, ts: float):
        for ep in self.episodes.values():
            if ep.ended is None:
                ep.ended = ts
                break
        self._save_episodes()

    def temporal_score(self, ts: float, now: Optional[float] = None) -> float:
        if now is None:
            now = time.time()
        age = max(0.0, now - ts)
        _hl = self.half_life if self.half_life else 604800.0
        decay = math.exp(-age / _hl)
        return 1.0 + self.recall_boost * decay

    def timeline(self, start: Optional[float] = None, end: Optional[float] = None,
                 kinds: Optional[Tuple[str, ...]] = None, limit: int = 50) -> List[Event]:
        if end is None:
            end = time.time()
        if start is None:
            start = end - 86400
        out = []
        for e in reversed(self.events):
            if e.ts < start or e.ts > end:
                continue
            if kinds and e.kind not in kinds:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def events_mentioning(self, subject: str, limit: int = 20) -> List[Event]:
        if not subject:
            return []
        s = subject.lower()
        out = []
        for e in reversed(self.events):
            if s in (e.summary or "").lower() or s in (e.ref or "").lower():
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    def since_last(self, subject: str) -> Optional[float]:
        events = self.events_mentioning(subject, limit=1)
        if not events:
            return None
        return time.time() - events[0].ts

    def add_deadline(self, ts: float, label: str) -> Deadline:
        did = self._hash_id("deadline", label, ts)
        d = Deadline(id=did, ts=ts, label=label, done=False, created=time.time())
        self.deadlines[did] = d
        self._save_deadlines()
        self.log_event("deadline", f"new deadline: {label}", ref=did,
                       meta={"due": ts})
        return d

    def list_deadlines(self, only_pending: bool = True) -> List[Deadline]:
        out = []
        for d in self.deadlines.values():
            if only_pending and d.done:
                continue
            out.append(d)
        out.sort(key=lambda d: d.ts)
        return out

    def complete_deadline(self, did: str) -> bool:
        if did in self.deadlines:
            self.deadlines[did].done = True
            self._save_deadlines()
            self.log_event("milestone", f"deadline done: {self.deadlines[did].label}", ref=did)
            return True
        return False

    def list_episodes(self, limit: int = 20) -> List[Episode]:
        out = list(self.episodes.values())
        out.sort(key=lambda e: e.started, reverse=True)
        return out[:limit]

    def circadian_summary(self) -> Dict[str, Any]:
        hourly = self.profile.get("hourly_activity") or [0] * 24
        if len(hourly) != 24:
            hourly = [0] * 24
        peak_hours = sorted(range(24), key=lambda h: hourly[h], reverse=True)[:3]
        quiet_hours = sorted(range(24), key=lambda h: hourly[h])[:3]
        return {
            "total_events": self.profile.get("total_events", 0),
            "peak_hours": peak_hours,
            "quiet_hours": quiet_hours,
            "hourly_distribution": hourly,
        }

    def first_event_ts(self) -> Optional[float]:
        return self.profile.get("first_event")

    def uptime_days(self) -> float:
        first = self.first_event_ts()
        if first is None:
            return 0.0
        return (time.time() - first) / 86400.0