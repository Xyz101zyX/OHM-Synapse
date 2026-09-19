# OHM_5_9_V5
# OHM_5_9_V4
import os
import urllib.parse as _urlparse
import sys
import time
import json
import hmac
import ctypes
import struct
import re
import math
import threading
import queue
import shlex
import base64
import unicodedata
import logging
import hashlib
from io import BytesIO
from typing import Dict, Any, List, Optional, Union, Tuple, Set, Callable
from dataclasses import dataclass, field, asdict
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import requests
import psutil
import bcrypt
import yaml
from ohm_chat import OHMChat
from ohm_embeddings import EmbeddingManager
from ohm_kairos import KairosEngine, humanize_delta, humanize_ts

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None  # type: ignore[assignment]

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    mqtt = None  # type: ignore[assignment]

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives.serialization import (
        load_pem_public_key, load_pem_private_key,
        Encoding, PrivateFormat, PublicFormat, NoEncryption
    )
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import gradio as gr
    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False
    gr = None  # type: ignore[assignment]

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore[assignment]

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import magpylib as mag
    HAS_MAGPYLIB = True
except ImportError:
    HAS_MAGPYLIB = False

from ohm.constants import *
from ohm.security import *
from ohm.crypto import *
from ohm.models import *
from ohm.flux import *
from ohm.fibonacci import *
from ohm.harmonic import *
from ohm.physics import *
from ohm.confidence import *
from ohm.grammar import *
from ohm.memory import *
from ohm.api import *
from ohm.user_mind import *
from ohm.llm import *
from ohm.mqtt_transport import *
from ohm.config import *
from ohm.middleware import *
from ohm.greek import *




class OHMSynapse:
    def __init__(self, config: Optional[OHMConfig] = None):
        if config is None:
            config = OHMConfig()
            if os.environ.get("OHM_TEST_MODE") == "1":
                import tempfile as _tf
                _testdir = _tf.mkdtemp(prefix="ohm_test_")
                config.memory_cfg = dict(config.memory_cfg)
                config.memory_cfg["persistence_file"] = os.path.join(_testdir, "mem.json")
                config.memory_cfg["audit_file"] = os.path.join(_testdir, "audit.jsonl")
                config.memory_cfg["export_file"] = os.path.join(_testdir, "export.json")
        self.config = config
        _thr_cfg = (self.config.raw.get("cognition", {}) or {}).get("thresholds", {}) or {}
        self._threshold_defaults = {
            "grounding": float(_thr_cfg.get("grounding", 0.20)),
            "confidence_respond": float(_thr_cfg.get("confidence_respond", 0.80)),
            "confidence_caution": float(_thr_cfg.get("confidence_caution", 0.50)),
        }
        self.thresholds = dict(self._threshold_defaults)
        _thr_path = Path(self.config.memory_cfg.get("persistence_file", "./mem.json")).parent / "thresholds.json"
        if _thr_path.exists():
            try:
                _over = json.loads(_thr_path.read_text(encoding="utf-8"))
                if isinstance(_over, dict):
                    for _k, _v in _over.items():
                        if _k in self.thresholds:
                            self.thresholds[_k] = float(_v)
            except Exception:
                pass
        self.grounding_threshold = self.thresholds["grounding"]
        self.memory = HoloMem4L(self.config)
        _emb_cfg = self.config.raw.get("embeddings", {}) or {}
        self.embeddings = EmbeddingManager(_emb_cfg, enabled=_emb_cfg.get("enabled", True))
        self.memory.attach_embeddings(self.embeddings)
        self.audit_log = AuditLog(self.config.memory_cfg.get("audit_file", "./ohm_audit_v1.jsonl"))
        self.symbolic = SymbolicResolver()
        self.middleware = OhmMiddleware(self.config)
        self.confidence = ConfidenceScorer(self.config.confidence_cfg)
        self.confidence.t_respond = self.thresholds["confidence_respond"]
        self.confidence.t_caution = self.thresholds["confidence_caution"]
        self.grammar = StructuralGrammar()
        self.verifier = ConfluenceVerifier()
        self.verifier.add_rule("type", "Fact", "source_url", None)
        self.verifier.add_rule("type", "PersonalNote", "user_confirmed", True)
        self.user_mind = MicroUserMind()
        self.signal = SignalAwareness()
        self.fib = FibonacciModule()
        self.mag = MagneticFieldModule()
        self.pit = PiTEngine()
        self.anomalies = AnomalyAnalyzer()
        self.flux_compiler = FluxCompiler()
        self.flux_arena = FluxArena()
        self.llm = OllamaAdapter(self.config) if self.config.llm_enabled else None
        self.api = PublicAPIManager()
        self.external_lookup_enabled = bool(self.config.raw.get("api_manager", {}).get("enabled", True))
        _node_key_file = self.config.security_cfg.get("node_key_file", "./ohm_node_keys.pem")
        self.genesis = GenesisCore("xyz101zyx", 1, key_file=_node_key_file)
        self.node_id = self.genesis.node_id or "local"
        self.crypto = GenesisCrypto("xyz101zyx", 1)
        self.running = True
        self.mqtt_queue: queue.Queue = queue.Queue()
        self.known_peers: Dict[str, Dict[str, Any]] = {}
        self.peer_responses: Dict[str, Any] = {}
        self.last_sync_time = time.time()
        self.harmonizer = InterAgentHarmonizer(self)
        sec = self.config.security_cfg
        self.query_limiter = RateLimiter(int(sec.get("max_queries_per_minute", 60)))
        self.exec_limiter = RateLimiter(int(sec.get("max_exec_per_minute", 20)))
        dist = self.config.distributed_cfg
        self.mqtt = MQTTClient(
            dist.get("mqtt_broker", "localhost"),
            int(dist.get("mqtt_port", 8883)),
            self.node_id,
            self.mqtt_queue,
            {
                "allow_public_broker": sec.get("allow_public_broker", False),
                "require_tls": sec.get("require_tls", True),
                "mqtt_user": dist.get("mqtt_user", ""),
                "mqtt_password": dist.get("mqtt_password", ""),
            },
        )
        if self.mqtt.enabled:
            threading.Thread(target=self._mqtt_loop, daemon=True).start()
            threading.Thread(target=self._sync_loop, daemon=True).start()
        self.chat = OHMChat(self, self.mqtt, self.node_id)
        _kairos_cfg = self.config.raw.get("kairos", {})
        _kairos_dir = Path(self.config.memory_cfg.get("persistence_file", "./mem.json")).parent
        self.kairos = KairosEngine(_kairos_cfg, _kairos_dir)
    
    def _llm_abstained(self, text: str) -> bool:
        if not text:
            return True
        t = text.lower().strip()
        head = t[:150]
        for m in ABSTAIN_MARKERS:
            if m in head:
                return True
        return False

    def _save_thresholds(self):
        p = Path(self.config.memory_cfg.get("persistence_file", "./mem.json")).parent / "thresholds.json"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.thresholds, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _apply_threshold_change(self, key, value):
        if key == "grounding":
            if not (0.0 <= value <= 1.0):
                return False, "grounding must be in [0, 1]"
            self.grounding_threshold = value
        elif key == "confidence_respond":
            if not (0.0 <= value <= 1.0):
                return False, "confidence_respond must be in [0, 1]"
            if value < self.thresholds.get("confidence_caution", 0.50):
                return False, "confidence_respond must be >= confidence_caution"
            self.confidence.t_respond = value
        elif key == "confidence_caution":
            if not (0.0 <= value <= 1.0):
                return False, "confidence_caution must be in [0, 1]"
            if value > self.thresholds.get("confidence_respond", 0.80):
                return False, "confidence_caution must be <= confidence_respond"
            self.confidence.t_caution = value
        else:
            return False, f"unknown threshold: {key}"
        old = self.thresholds.get(key)
        self.thresholds[key] = value
        self._save_thresholds()
        self._emit_audit({"event": "threshold_changed", "key": key, "old": old, "new": value})
        return True, f"{key}: {old} -> {value}"

    def _reset_threshold(self, key=None):
        if key is None:
            keys = list(self._threshold_defaults.keys())
        else:
            if key not in self._threshold_defaults:
                return False, f"unknown threshold: {key}"
            keys = [key]
        for k in keys:
            self._apply_threshold_change(k, self._threshold_defaults[k])
        return True, f"reset: {keys}"

    def _emit_audit(self, event: Dict[str, Any]):
        try:
            self.audit_log.append(event, signer=self.genesis.sign)
        except Exception as e:
            LOG.warning(f"audit failed: {e}")

    def _mqtt_loop(self):
        while self.running:
            try:
                msg = self.mqtt_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                SandboxGuard.enter_remote()
                self._handle_mqtt_message(msg)
            except Exception as e:
                LOG.warning(f"mqtt handler error: {e}")
            finally:
                SandboxGuard.exit_remote()

    def _handle_mqtt_message(self, msg: Dict[str, Any]):
        topic = msg.get("topic", "")
        payload = msg.get("payload", {})
        if topic == "ohm/network/discovery":
            peer = payload.get("node_id")
            if peer and peer != self.node_id and not self._is_revoked(peer):
                is_new = peer not in self.known_peers
                self.known_peers[peer] = payload
                if is_new:
                    self.mqtt.publish("ohm/network/discovery", {
                        "node_id": self.node_id,
                        "version": self.config.version,
                        "public_key": (self.genesis.public_key_pem or b"").decode(errors="ignore"),
                        "timestamp": time.time(),
                    })
        elif topic == f"ohm/network/query/{self.node_id}":
            sender = payload.get("from")
            query_text = payload.get("query", "")
            if sender and query_text and not self._is_revoked(sender):
                if not self.query_limiter.allow(f"mqtt:{sender}"):
                    return
                response = self.think(query_text, origin="mqtt")
                self.mqtt.publish(f"ohm/network/response/{sender}", {
                    "from": self.node_id,
                    "data": CitationFormatter.format(response),
                })
        elif topic == f"ohm/network/response/{self.node_id}":
            sender = payload.get("from")
            if sender and not self._is_revoked(sender):
                self.peer_responses[sender] = payload.get("data")
        elif topic == "ohm/delta/sync":
            sender = payload.get("node_id")
            if not sender or sender == self.node_id or self._is_revoked(sender):
                return
            if not payload.get("encrypted"):
                return
            sig = payload.get("signature", "")
            pub = payload.get("public_key", "").encode()
            data_field = payload.get("data", "")
            if not sig or not pub:
                LOG.warning(f"delta missing signature from {sender}")
                return
            if not self.genesis.verify(data_field.encode(), sig, pub):
                LOG.warning(f"delta signature invalid from {sender}")
                return
            try:
                delta = self.crypto.decrypt(data_field)
                self._apply_remote_delta(sender, delta)
            except Exception as e:
                LOG.debug(f"delta rejected: {type(e).__name__}")
        elif topic.startswith("ohm/chat/handshake/"):
            self.chat.handle_handshake(payload)
        elif topic.startswith("ohm/chat/msg/"):
            result = self.chat.receive(payload)
            if result and result.get("status") == "RECEIVED":
                self._emit_audit({"event": "chat_inbound", "peer": result["peer"]})
        elif topic.startswith("ohm/revoke/"):
            rev = payload.get("revocation", {})
            signer = rev.get("signer")
            if signer and signer in self.known_peers:
                pub = self.known_peers[signer].get("public_key", "").encode()
                msg_bytes = f"REVOKE:{rev.get('target')}:{rev.get('timestamp')}".encode()
                if pub and self.genesis.verify(msg_bytes, rev.get("signature", ""), pub):
                    self.genesis.blacklist.add(rev["target"])
                    self._emit_audit({"event": "revoke", "target": rev["target"], "signer": signer})

    def _apply_remote_delta(self, sender: str, delta: Any):
        if not isinstance(delta, dict):
            LOG.warning(f"delta from {sender} rejected: not a dict")
            self._emit_audit({"event": "delta_rejected", "from": sender, "reason": "not_a_dict"})
            return
        allowed_layers = tuple(self.config.distributed_cfg.get("sync_layers",
                                                              [MemoryLayer.FACT_EXTERNAL, MemoryLayer.PERSONAL_RECORD]))
        filtered: Dict[str, Any] = {}
        for k, v in delta.items():
            if not isinstance(v, dict):
                continue
            if v.get("layer") in allowed_layers:
                v["metadata"] = v.get("metadata", {})
                v["metadata"]["remote_origin"] = sender
                filtered[k] = v
        if filtered:
            self.memory.apply_delta(filtered)
            self._emit_audit({"event": "delta_applied", "from": sender, "keys": list(filtered.keys())})

    def _sync_loop(self):
        interval = float(self.config.distributed_cfg.get("sync_interval", 30))
        while self.running:
            try:
                if self.mqtt.enabled:
                    self.mqtt.publish("ohm/network/discovery", {
                        "node_id": self.node_id,
                        "version": self.config.version,
                        "public_key": (self.genesis.public_key_pem or b"").decode(errors="ignore"),
                        "timestamp": time.time(),
                    })
                    delta = self.memory.get_delta(self.last_sync_time)
                    if delta:
                        encrypted = self.crypto.encrypt(delta)
                        sig = self.genesis.sign(encrypted.encode())
                        self.mqtt.publish("ohm/delta/sync", {
                            "node_id": self.node_id,
                            "encrypted": True,
                            "data": encrypted,
                            "signature": sig,
                            "public_key": (self.genesis.public_key_pem or b"").decode(errors="ignore"),
                        })
                        self.last_sync_time = time.time()
            except Exception as e:
                LOG.warning(f"sync error: {e}")
            time.sleep(interval)

    def _is_revoked(self, node_id: str) -> bool:
        return node_id in self.genesis.blacklist

    def _recognize_user(self, query: str) -> str:
        h = self.genesis.sign_query(query)
        profile = json.loads(self.user_mind.get_profile())
        top = profile.get("top_domain", "unknown")
        avg = float(profile.get("avg_cognitive_load", 0) or 0)
        return f"{top}_{h % 1000}_{int(avg)}"

    def _stage1_recall(self, query: str) -> List[Dict[str, Any]]:
        hits = self.memory.recall_hybrid(query, top_k=10, embedder=self.embeddings)
        now = time.time()
        for h in hits:
            ts = h.get("created") or now
            tf = self.kairos.temporal_score(ts, now)
            h["temporal_score"] = round(tf, 4)
            base = h.get("hybrid_score", h.get("score", 0.0))
            h["final_score"] = round(base * tf, 4)
        hits.sort(key=lambda h: h.get("final_score", 0.0), reverse=True)
        return hits[:5]

    def _stage1_recall_expanded(self, query: str) -> List[Dict[str, Any]]:
        hits = self._stage1_recall(query)
        if hits and hits[0].get("score", 0.0) >= 0.30:
            return hits
        if not hits:
            return hits
        q_tokens = set(w.lower() for w in re.findall(r"\w+", query))
        entities = set()
        for h in hits[:3]:
            content = h.get("content") or ""
            for token in re.findall(r"\b[A-Z][a-z]+\b", content):
                tl = token.lower()
                if tl not in q_tokens and len(token) >= 3:
                    entities.add(tl)
        if not entities:
            return hits
        seen_ids = {h.get("id") for h in hits}
        extra = []
        for ent in entities:
            second = self.memory.recall(ent, top_k=3)
            for s in second:
                if s.get("id") in seen_ids:
                    continue
                seen_ids.add(s.get("id"))
                s["_hop_entity"] = ent
                extra.append(s)
        merged = hits + extra
        merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return merged[:10]

    def _stage2_grounding(self, query: str, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not memories:
            return {"grounded": False, "action": "external_lookup", "sources": []}
        if self._is_personal_query(query):
            candidates = [
                m for m in memories
                if m.get("layer") == MemoryLayer.PERSONAL_RECORD
                and self._subject_matches_memory(query, m)
                and m.get("score", 0.0) >= self.grounding_threshold
            ]
            if not candidates:
                return {"grounded": False, "action": "subject_mismatch", "sources": []}
            top = max(candidates, key=lambda m: m.get("score", 0.0))
            sources = []
            for s in top.get("sources", []):
                try:
                    sources.append(Source(**s))
                except TypeError:
                    pass
            return {"grounded": True, "action": "ok_personal",
                    "sources": sources, "memory": top}

        top = memories[0]
        if top.get("layer") == MemoryLayer.EPHEMERAL:
            return {"grounded": False, "action": "reject_ephemeral", "sources": []}
        if top.get("score", 0.0) < self.grounding_threshold:
            return {"grounded": False, "action": "external_lookup", "sources": []}
        sources = []
        for m in memories:
            for s in m.get("sources", []):
                try:
                    sources.append(Source(**s))
                except TypeError:
                    sources.append(Source(kind=s.get("kind", "unknown"),
                                          ref=s.get("ref", "unknown"),
                                          timestamp=s.get("timestamp", time.time()),
                                          detail=s.get("detail", ""),
                                          layer=s.get("layer", MemoryLayer.PERSONAL_RECORD)))
        return {"grounded": True, "action": "ok", "sources": sources, "memory": top}

    def _is_personal_query(self, query: str) -> bool:
        markers = (" my ", " i ", " me ", " mine ", " our ", " we ",
                   " myself ", " ourselves ",
                   " i'm ", " i've ", " i'd ", " i'll ")
        q_lower = " " + query.lower().strip() + " "
        return any(marker in q_lower for marker in markers)

    def _subject_matches_memory(self, query: str, memory: dict) -> bool:
        content = (memory.get("content") or "").lower()
        if not content:
            return False
        q_tokens = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
        q_tokens -= {
            "what", "when", "where", "which", "who", "whom", "whose",
            "why", "how", "the", "and", "or", "but", "for", "with",
            "from", "into", "this", "that", "these", "those", "there",
            "here", "some", "any", "all", "are", "was", "were", "been",
            "being", "have", "has", "had", "does", "did", "will", "would",
            "should", "could", "can", "may", "might", "must", "your",
            "yours", "their", "theirs", "our", "ours", "its",
            "name", "called", "please", "tell", "know", "think",
        }
        if not q_tokens:
            return True
        return any(tok in content for tok in q_tokens)

    def _stage2b_external_lookup(self, query: str) -> List[Source]:
        if not self.external_lookup_enabled:
            return []
        sources = []
        for attempt in range(2):
            try:
                summary = self.api.get_wikipedia_summary(query) or {}
                if isinstance(summary, dict) and summary.get("extract"):
                    url = summary.get("source_url") or \
                          f"https://en.wikipedia.org/wiki/{_urlparse.quote(query)}"
                    extract = summary["extract"]
                    if self._extract_matches_query(query, extract):
                        sources.append(Source(kind="wikipedia", ref=url, timestamp=time.time(),
                                              detail=extract[:200], layer=MemoryLayer.FACT_EXTERNAL))
                        return sources
                break
            except Exception as e:
                LOG.warning(f"wiki summary attempt {attempt} failed: {e}")
                time.sleep(0.5)
        try:
            summary = self.api.search_wikipedia(query) or {}
            if isinstance(summary, dict) and summary.get("extract"):
                url = summary.get("source_url") or \
                      f"https://en.wikipedia.org/wiki/{_urlparse.quote(query)}"
                extract = summary["extract"]
                if self._extract_matches_query(query, extract):
                    sources.append(Source(kind="wikipedia", ref=url, timestamp=time.time(),
                                          detail=extract[:200], layer=MemoryLayer.FACT_EXTERNAL))
        except Exception as e:
            LOG.warning(f"wiki search failed: {e}")
        return sources

    def _extract_matches_query(self, query: str, extract: str, threshold: float = 0.15) -> bool:
        q_tokens = set(w for w in re.findall(r"\w+", query.lower()) if len(w) > 2)
        q_tokens = {w for w in q_tokens if w not in self._SUBJECT_STOPWORDS}
        if not q_tokens:
            return False
        extract_lower = extract.lower()
        matched = sum(1 for t in q_tokens if t in extract_lower)
        return (matched / len(q_tokens)) >= threshold

    def _stage3_reasoning(self, query: str, context: List[Dict[str, Any]],
                          use_llm: bool) -> Dict[str, Any]:
        symbolic = self.symbolic.evaluate(query)
        candidate = None
        llm_used = False
        if "calculate" in query.lower() and not symbolic.startswith("symbolic_error"):
            return {"candidate": symbolic, "llm_used": False, "symbolic": symbolic}
        if use_llm and self.llm is not None:
            llm_out = None
            if context:
                context_text = "\n".join(c.get("content", "")[:300] for c in context[:3])
                prompt = (f"Context:\n{context_text}\n\nQuestion: {query}\n\n"
                          f"Answer strictly based on the context above. "
                          f"If the context does not answer, say 'I do not have that information'.")
                llm_out, _ = self.llm.generate(prompt)
            elif not self._is_personal_query(query):
                prompt = f"Question: {query}\n\nAnswer concisely and factually."
                llm_out, _ = self.llm.generate(prompt)
            if llm_out and "DIAGNOSTIC" not in llm_out:
                candidate = llm_out.strip()
                llm_used = True
        return {"candidate": candidate, "llm_used": llm_used, "symbolic": symbolic}

    def _stage4_grammar(self, candidate: str, origin_layer: str,
                        sources: List[Source]) -> Tuple[bool, str, Dict[str, Any]]:
        note_type = "PersonalNote" if origin_layer == MemoryLayer.PERSONAL_RECORD else (
            "Fact" if origin_layer == MemoryLayer.FACT_EXTERNAL else "Inference")
        note: Dict[str, Any] = {"type": note_type, "statement": candidate}
        if note_type == "Fact" and sources:
            note["source_url"] = sources[0].ref
            note["source_kind"] = sources[0].kind
        if note_type == "PersonalNote":
            note["user_confirmed"] = bool(sources and sources[0].kind == "user")
        if note_type == "Inference":
            note["derived_from"] = [s.ref for s in sources] or ["llm"]
        ok, reason = self.grammar.validate(note)
        return ok, reason, note

    def _stage5_confluence(self, candidate_note: Dict[str, Any],
                           memories: List[Dict[str, Any]],
                           check_candidate: bool = True) -> Tuple[bool, List[str]]:
        conflicts = []
        if check_candidate:
            cand_stmt = (candidate_note.get("statement") or "").strip().lower()
            if cand_stmt:
                cand_subject = self._extract_subject(cand_stmt)
                for m in memories:
                    existing_stmt = (m.get("content") or "").strip().lower()
                    if not existing_stmt:
                        continue
                    if existing_stmt[:120] == cand_stmt[:120]:
                        continue
                    exist_subject = self._extract_subject(existing_stmt)
                    if cand_subject and exist_subject and cand_subject == exist_subject:
                        if not self._semantically_compatible(cand_stmt, existing_stmt):
                            conflicts.append(
                                f"candidate_vs_memory subject='{cand_subject}'")
        for i, m1 in enumerate(memories):
            s1 = (m1.get("content") or "").strip().lower()
            if not s1:
                continue
            subj1 = self._extract_subject(s1)
            if not subj1:
                continue
            for m2 in memories[i + 1:]:
                s2 = (m2.get("content") or "").strip().lower()
                if not s2:
                    continue
                subj2 = self._extract_subject(s2)
                if subj1 == subj2 and not self._semantically_compatible(s1, s2):
                    conflicts.append(
                        f"memory_vs_memory subject='{subj1}': '{s1[:60]}' vs '{s2[:60]}'")
        return (len(conflicts) == 0), conflicts
    
    _SUBJECT_STOPWORDS = {
        "the", "and", "for", "with", "from", "into", "this", "that", "these",
        "those", "there", "here", "some", "any", "all", "are", "was", "were",
        "been", "being", "have", "has", "had", "does", "did", "will", "would",
        "should", "could", "can", "may", "might", "must", "since", "however",
        "based", "context", "answer", "question", "given", "what", "when",
        "where", "which", "who", "whom", "whose", "why", "how",
    }

    def _extract_subject(self, text: str) -> str:
        m = re.match(r"(?:the|my|user'?s?)\s+(\w+)", text, re.UNICODE)
        if m:
            word = m.group(1)
            if word not in self._SUBJECT_STOPWORDS:
                return word
        tokens = [t for t in re.findall(r"\w+", text.lower())
                  if len(t) > 3 and t not in self._SUBJECT_STOPWORDS]
        return tokens[0] if tokens else ""
    
    def _semantically_compatible(self, a: str, b: str) -> bool:
        na = set(re.findall(r"\w+", a))
        nb = set(re.findall(r"\w+", b))
        if not na or not nb:
            return True
        diff_a = na - nb
        diff_b = nb - na
        if not diff_a and not diff_b:
            return True
        short_diffs = (len(diff_a) <= 2 and len(diff_b) <= 2)
        both_have_value = (len(diff_a) > 0 and len(diff_b) > 0)
        if short_diffs and both_have_value:
            return False
        return True

    def _stage6_confidence(self, query: str, memories: List[Dict[str, Any]],
                           sources: List[Source], verifications: Dict[str, Any],
                           llm_used: bool) -> float:
        return self.confidence.score(query, memories, sources, verifications, llm_used)

    def _stage7_decision(self, conf: float, conflicts: List[str]) -> str:
        if conflicts:
            return "conflict"
        return self.confidence.decision(conf)

    def _build_response(self, decision: str, candidate: str, sources: List[Source],
                        conf: float, layer: str, verifications: Dict[str, Any],
                        llm_used: bool, conflicts: Optional[List[str]] = None) -> Response:
        if decision == "conflict":
            text = ("I have conflicting memories. Please resolve before I answer:\n"
                    + "\n".join(f"- {c}" for c in conflicts or []))
            return Response(text=text, status="CONFLICT", layer=MemoryLayer.INFERENCE,
                            confidence=conf, sources=sources, verifications=verifications,
                            llm_used=llm_used)
        if decision == "abstain":
            return Response(text="I do not have that information with sufficient confidence.",
                            status="ABSTAIN", layer=MemoryLayer.INFERENCE,
                            confidence=conf, sources=sources, verifications=verifications,
                            llm_used=llm_used)
        if decision == "caution":
            return Response(text=candidate + "\n\n[caution: low confidence, treat as tentative]",
                            status="CAUTION", layer=layer,
                            confidence=conf, sources=sources, verifications=verifications,
                            llm_used=llm_used)
        return Response(text=candidate, status="OK", layer=layer,
                        confidence=conf, sources=sources, verifications=verifications,
                        llm_used=llm_used)

    def think(self, query: str, origin: str = "local") -> Response:
        query = (query or "").strip()
        if not query:
            return Response(text="empty query", status="EMPTY",
                            layer=MemoryLayer.EPHEMERAL, confidence=0.0)

        if origin == "local" and not self.query_limiter.allow("local"):
            return Response(text="rate limit exceeded", status="RATE_LIMITED",
                            layer=MemoryLayer.EPHEMERAL, confidence=0.0)

        try:
            _kind = "command" if query.startswith("/") else "query"
            self.kairos.log_event(_kind, query[:200], ref=origin, meta={})
            _kairos_logged_top = True
        except Exception:
            _kairos_logged_top = False
        if query.startswith("/"):
            return self._handle_command(query)

        memories = self._stage1_recall_expanded(query)
        grounding = self._stage2_grounding(query, memories)

        external_sources: List[Source] = []
        if not grounding["grounded"] and not self._is_personal_query(query):
            external_sources = self._stage2b_external_lookup(query)
            for s in external_sources:
                key = f"auto_{int(s.timestamp)}_{hashlib.md5(s.ref.encode()).hexdigest()[:6]}"
                self.memory.store_memory(
                    key=key, content=s.detail or s.ref,
                    layer=MemoryLayer.FACT_EXTERNAL, sources=[s],
                    reliability=0.85,
                )

        if (grounding.get("grounded")
                and grounding.get("action") == "ok_personal"
                and grounding.get("memory")):
            _mem = grounding["memory"]
            return self._build_response(
                "respond", _mem.get("content", ""),
                list(grounding.get("sources", [])),
                float(_mem.get("score", 0.0)),
                MemoryLayer.PERSONAL_RECORD,
                {"grounding_ok": True, "direct_memory": True},
                False,
            )

        policy = self.signal.get_adaptation_policy()
        use_llm = bool(policy.get("use_llm", True))

        context_for_llm = []
        if grounding["grounded"] and grounding.get("memory"):
            context_for_llm.append(grounding["memory"])
        for s in external_sources:
            context_for_llm.append({"content": s.detail or s.ref, "layer": s.layer})

        reasoning = self._stage3_reasoning(query, context_for_llm, use_llm)
        candidate = reasoning.get("candidate") or ""
        llm_used = bool(reasoning.get("llm_used"))

        # personal_memory_fallback
        if not candidate and not llm_used and grounding.get("memory"):
            _mem = grounding["memory"]
            if _mem.get("layer") == MemoryLayer.PERSONAL_RECORD and _mem.get("score", 0.0) >= 0.30:
                candidate = _mem.get("content", "")

        if llm_used and self._llm_abstained(candidate):
            return self._build_response(
                "abstain", "", all_sources_pre := list(grounding.get("sources", [])) + external_sources,
                0.0, MemoryLayer.INFERENCE,
                {"grounding_ok": bool(grounding.get("grounded")),
                 "grammar_ok": True, "confluence_ok": True, "residual": 0.15,
                 "llm_abstained": True},
                llm_used=True,
            )

        all_sources = list(grounding.get("sources", [])) + external_sources

        if llm_used and not all_sources and not self._is_personal_query(query):
            all_sources.append(Source(kind="llm-general",
                                      ref=self.config.llm_cfg.get("model_name", "llm"),
                                      timestamp=time.time(),
                                      detail="general knowledge answer",
                                      layer=MemoryLayer.INFERENCE))

        if not candidate and not all_sources:
            return self._build_response("abstain", "", all_sources, 0.0,
                                        MemoryLayer.INFERENCE,
                                        {"grounding_ok": False, "grammar_ok": False,
                                         "confluence_ok": True, "residual": 0.0},
                                        False)

        if not candidate and all_sources:
            detail = all_sources[0].detail
            if detail and len(detail.strip()) > 0:
                candidate = detail
                llm_used = False
            else:
                return self._build_response(
                    "abstain", "", all_sources, 0.0,
                    MemoryLayer.INFERENCE,
                    {"grounding_ok": bool(grounding.get("grounded")),
                     "grammar_ok": True, "confluence_ok": True,
                     "residual": 0.15, "no_content": True},
                    llm_used=False,
                )

        if llm_used:
            origin_layer = MemoryLayer.INFERENCE
        elif external_sources:
            origin_layer = MemoryLayer.FACT_EXTERNAL
        elif grounding.get("memory"):
            origin_layer = grounding["memory"].get("layer", MemoryLayer.INFERENCE)
        else:
            origin_layer = MemoryLayer.INFERENCE

        grammar_ok, grammar_reason, note = self._stage4_grammar(candidate, origin_layer, all_sources)
        confluence_ok, conflicts = self._stage5_confluence(
            note, memories, check_candidate=(not llm_used))
        
        verifications = {
            "grounding_ok": bool(grounding.get("grounded")),
            "grammar_ok": grammar_ok,
            "confluence_ok": confluence_ok,
            "residual": 0.0 if external_sources else 0.15,
            "grammar_reason": grammar_reason,
        }

        conf = self._stage6_confidence(query, memories, all_sources, verifications, llm_used)
        decision = self._stage7_decision(conf, conflicts)

        response = self._build_response(decision, candidate, all_sources, conf,
                                        origin_layer, verifications, llm_used, conflicts)

        if decision == "respond" and all_sources:
            s = all_sources[0]
            key = f"resp_{int(time.time()*1000)}_{hashlib.md5((s.ref or '').encode()).hexdigest()[:6]}"
            self.memory.store_memory(
                key=key, content=candidate[:500],
                layer=MemoryLayer.INFERENCE,
                sources=all_sources, reliability=0.3,
            )

        user_id = self._recognize_user(query)
        self.user_mind.update(query)

        self._emit_audit({
            "event": "think",
            "query": query,
            "origin": origin,
            "user_id": user_id,
            "status": response.status,
            "confidence": response.confidence,
            "layer": response.layer,
            "llm_used": response.llm_used,
        })
        return response

    def _handle_command(self, query: str) -> Response:
        parts = query.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/audit":
            entries = self.memory.audit(arg or None)
            text = "\n".join(
                f"- {e['id']} | {e['layer']} | r={e['reliability']} | {e['content'][:80]}"
                for e in entries[:50]
            ) or "no entries"
            return Response(text=text, status="AUDIT", layer=MemoryLayer.PERSONAL_RECORD,
                            confidence=1.0)

        if cmd == "/forget":
            if not arg:
                return Response(text="usage: /forget <id>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            ok = self.memory.forget(arg)
            self._emit_audit({"event": "forget", "key": arg, "ok": ok})
            return Response(text=f"forgot {arg}: {ok}", status="FORGET",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/correct":
            tokens = arg.split(maxsplit=1)
            if len(tokens) < 2:
                return Response(text="usage: /correct <id> <new content>",
                                status="USAGE", layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            key, new_content = tokens[0], tokens[1]
            src = Source(kind="user", ref="user", timestamp=time.time(), layer=MemoryLayer.PERSONAL_RECORD)
            ok = self.memory.correct(key, new_content, MemoryLayer.PERSONAL_RECORD,
                                     sources=[src], user_confirmed=True)
            self._emit_audit({"event": "correct", "key": key, "ok": ok})
            return Response(text=f"corrected {key}: {ok}", status="CORRECT",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/export":
            data = self.memory.export()
            path = self.config.memory_cfg.get("export_file", "./ohm_memory_export.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return Response(text=f"exported to {path}", status="EXPORT",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/remember":
            if not arg:
                return Response(text="usage: /remember <content>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            src = Source(kind="user", ref="user", timestamp=time.time(), layer=MemoryLayer.PERSONAL_RECORD)
            key = f"user_{int(time.time()*1000)}_{hashlib.md5(arg.encode()).hexdigest()[:6]}"
            ok = self.memory.store_memory(key, arg, MemoryLayer.PERSONAL_RECORD,
                                          sources=[src], user_confirmed=True)
            self._emit_audit({"event": "remember", "key": key, "ok": ok})
            return Response(text=f"remembered: {ok}", status="REMEMBER",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/promote":
            tokens = arg.split()
            if len(tokens) < 2:
                return Response(text="usage: /promote <id> <layer>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            key, layer = tokens[0], tokens[1]
            ok = self.memory.promote(key, layer, user_confirmed=(layer == MemoryLayer.PERSONAL_RECORD))
            self._emit_audit({"event": "promote", "key": key, "layer": layer, "ok": ok})
            return Response(text=f"promote {key}->{layer}: {ok}", status="PROMOTE",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/revoke":
            if not arg:
                return Response(text="usage: /revoke <peer>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            if arg not in self.known_peers:
                return Response(text=f"peer not found: {arg}", status="REVOKE_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            target = arg
            ts = time.time()
            message = f"REVOKE:{target}:{ts}".encode()
            signature = self.genesis.sign(message)
            rev = {"target": target, "signature": signature, "timestamp": ts, "signer": self.node_id}
            self.mqtt.publish(f"ohm/revoke/{target}", {"revocation": rev})
            self.genesis.blacklist.add(target)
            self._emit_audit({"event": "revoke_sent", "target": target})
            return Response(text=f"revocation propagated to {target}", status="REVOKE",
                            layer=MemoryLayer.PERSONAL_RECORD, confidence=1.0)

        if cmd == "/fib":
            try:
                n = int(arg.strip())
                if n < 0:
                    return Response(text="n must be >= 0", status="FIB_ERROR",
                                    layer=MemoryLayer.EPHEMERAL, confidence=0.0)
                if n > 100000:
                    return Response(text="n too large (max 100000)", status="FIB_ERROR",
                                    layer=MemoryLayer.EPHEMERAL, confidence=0.0)
                value = self.fib.fib(n)
                digits = len(str(value))
                preview = str(value)[:64] + ("..." if digits > 64 else "")
                text = f"F({n}) = {preview} ({digits} digits)"
                return Response(text=text, status="FIB",
                                layer=MemoryLayer.INFERENCE, confidence=0.95)
            except ValueError:
                return Response(text="usage: /fib <integer>", status="FIB_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            except Exception as e:
                return Response(text=f"error: {e}", status="FIB_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)

        if cmd == "/psi":
            if not HAS_NUMPY:
                return Response(text="numpy required", status="PSI_UNAVAILABLE",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            vals = [float(v.get("reliability", 0.5)) for v in self.memory.store.values()]
            if len(vals) < 3:
                vals += [0.0] * (3 - len(vals))
            g = GreekFramework(alfa=[np.array(vals)], beta_func=lambda x, m, s: x)
            return Response(text=f"psi={g.calculate_psi():.4f}", status="PSI",
                            layer=MemoryLayer.INFERENCE, confidence=0.5)

        if cmd == "/weather":
            data = self.api.get_weather_openmeteo()
            if "error" in data:
                return Response(text=str(data), status="WEATHER_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            cw = data.get("current_weather", {})
            src = Source(kind="api", ref="https://api.open-meteo.com/v1/forecast",
                         timestamp=time.time(), detail="open-meteo", layer=MemoryLayer.FACT_EXTERNAL)
            return Response(text=f"temperature={cw.get('temperature')}C wind={cw.get('windspeed')}km/h",
                            status="WEATHER", layer=MemoryLayer.FACT_EXTERNAL,
                            confidence=0.9, sources=[src])

        if cmd == "/wiki":
            if not arg:
                return Response(text="usage: /wiki <topic>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            summary = self.api.get_wikipedia_summary(arg) or {}
            if "error" in summary or not summary.get("extract"):
                alt = unicodedata.normalize("NFKD", arg).encode("ASCII", "ignore").decode()
                summary = self.api.get_wikipedia_summary(alt) or {}
            if not isinstance(summary, dict) or not summary.get("extract"):
                return Response(text=f"not found: {arg}", status="WIKI_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            url = summary.get("source_url") or f"https://en.wikipedia.org/wiki/{_urlparse.quote(arg)}"
            src = Source(kind="wikipedia", ref=url, timestamp=time.time(),
                         detail=arg, layer=MemoryLayer.FACT_EXTERNAL)
            return Response(text=summary["extract"][:600], status="WIKI",
                            layer=MemoryLayer.FACT_EXTERNAL, confidence=0.9, sources=[src])

        if cmd == "/peers":
            if not self.known_peers:
                return Response(text="no peers", status="PEERS",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            text = "\n".join(f"- {pid} v{p.get('version', '?')}" for pid, p in self.known_peers.items())
            return Response(text=text, status="PEERS", layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/ask":
            tokens = arg.split(maxsplit=1)
            if len(tokens) < 2:
                return Response(text="usage: /ask <peer> <query>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            peer, q = tokens
            if peer not in self.known_peers:
                return Response(text=f"peer not found: {peer}", status="ASK_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            self.mqtt.publish(f"ohm/network/query/{peer}", {"from": self.node_id, "query": q})
            return Response(text=f"query sent to {peer}", status="ASK_SENT",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/read":
            if arg in self.peer_responses:
                return Response(text=self.peer_responses.pop(arg), status="READ",
                                layer=MemoryLayer.FACT_EXTERNAL, confidence=0.7)
            return Response(text=f"no response from {arg}", status="READ_EMPTY",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/exec":
            if not self.exec_limiter.allow("local"):
                return Response(text="exec rate limit", status="RATE_LIMITED",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)
            try:
                code = self.flux_compiler.compile(arg)
                result = FluxExecutor.run(code)
                self._emit_audit({"event": "flux_exec", "code_hash": hashlib.md5(arg.encode()).hexdigest()})
                return Response(text=f"flux result={result}", status="FLUX",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.5)
            except Exception as e:
                return Response(text=f"flux error: {e}", status="FLUX_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)

        if cmd == "/anomaly":
            try:
                info = self.anomalies.get_anomaly(int(arg))
                return Response(text=json.dumps(info), status="ANOMALY",
                                layer=MemoryLayer.INFERENCE, confidence=0.5)
            except Exception:
                return Response(text="usage: /anomaly <id>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/mag":
            try:
                payload = json.loads(arg)
                B = self.mag.field_from_wire(payload.get("point", [0, 0, 0]),
                                             payload.get("current", 1.0),
                                             payload.get("start", [-1, 0, 0]),
                                             payload.get("end", [1, 0, 0]))
                return Response(text=json.dumps(B), status="MAG",
                                layer=MemoryLayer.INFERENCE, confidence=0.5)
            except Exception as e:
                return Response(text=str(e), status="MAG_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=0.0)

        if cmd == "/pit":
            return Response(text=json.dumps(self.pit.get_status()), status="PIT",
                            layer=MemoryLayer.INFERENCE, confidence=0.5)

        if cmd == "/dashboard":
            data = ContextualCollector.collect_all()
            stats = self.middleware.scheduler.monitor()
            text = (
                f"weather: {data.get('weather', {})}\n"
                f"geo: {data.get('geolocation', {})}\n"
                f"net: {data.get('network', {})}\n"
                f"cpu={stats['cpu']:.1f}% ram={stats['ram']:.1f}%"
            )
            return Response(text=text, status="DASHBOARD",
                            layer=MemoryLayer.FACT_EXTERNAL, confidence=0.8)

        if cmd == "/chat_status":
            s = self.chat.status()
            text = ("chat enabled: " + str(s["enabled"]) + "\n"
                    "node: " + s["node_id"] + "\n"
                    "sessions: " + str(s["active_sessions"]) + "\n"
                    "peers: " + (", ".join(s["peers"]) or "none"))
            return Response(text=text, status="CHAT_STATUS",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/chat_handshake":
            if not arg:
                return Response(text="usage: /chat_handshake <peer_id>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            ok = self.chat.send_handshake(arg.strip())
            return Response(text=f"handshake sent: {ok}", status="CHAT_HANDSHAKE",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/chat_send":
            tokens = arg.split(maxsplit=1)
            if len(tokens) < 2:
                return Response(text="usage: /chat_send <peer_id> <msg>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            peer, msg = tokens[0], tokens[1]
            result = self.chat.send(peer, msg)
            return Response(text=str(result), status=result.get("status", "CHAT_ERROR"),
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/chat_history":
            if not arg:
                return Response(text="usage: /chat_history <peer_id>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            hist = self.chat.get_history(arg.strip())
            if not hist:
                return Response(text="no history", status="CHAT_HISTORY",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            text = "\n".join(f"[{e['role']}] {e['content'][:80]}" for e in hist)
            return Response(text=text, status="CHAT_HISTORY",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/chat_peers":
            peers = self.chat.list_peers()
            text = "\n".join(peers) if peers else "no active sessions"
            return Response(text=text, status="CHAT_PEERS",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/kairo":
            up = self.kairos.uptime_days()
            ev = self.kairos.profile.get("total_events", 0)
            eps = len(self.kairos.episodes)
            dl = len([d for d in self.kairos.deadlines.values() if not d.done])
            text = (
                f"uptime: {up:.2f} days\n"
                f"events: {ev}\n"
                f"episodes: {eps}\n"
                f"pending deadlines: {dl}"
            )
            return Response(text=text, status="KAIRO",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/timeline":
            hours = 24
            if arg.strip():
                try:
                    hours = int(arg.strip())
                except ValueError:
                    pass
            start = time.time() - hours * 3600
            events = self.kairos.timeline(start=start, limit=30)
            if not events:
                return Response(text=f"no events in last {hours}h", status="TIMELINE",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            lines = [f"last {hours}h - {len(events)} events:"]
            for ent in events:
                lines.append(f"  [{humanize_ts(ent.ts)}] {ent.kind}: {ent.summary[:80]}")
            return Response(text="\n".join(lines), status="TIMELINE",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/when":
            if not arg.strip():
                return Response(text="usage: /when <subject>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            events = self.kairos.events_mentioning(arg.strip(), limit=5)
            if not events:
                return Response(text=f"no events mention '{arg.strip()}'", status="WHEN",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            lines = [f"events mentioning '{arg.strip()}':"]
            for ent in events:
                ago = humanize_delta(time.time() - ent.ts)
                lines.append(f"  {humanize_ts(ent.ts)} ({ago} ago) - {ent.kind}: {ent.summary[:80]}")
            return Response(text="\n".join(lines), status="WHEN",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/since":
            if not arg.strip():
                return Response(text="usage: /since <subject>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            delta = self.kairos.since_last(arg.strip())
            if delta is None:
                return Response(text=f"no events mention '{arg.strip()}'", status="SINCE",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            return Response(text=f"last mention of '{arg.strip()}': {humanize_delta(delta)} ago",
                            status="SINCE", layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/episodes":
            eps_list: list = self.kairos.list_episodes(limit=10)
            if not eps_list:
                return Response(text="no episodes yet", status="EPISODES",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            lines = [f"{len(eps_list)} recent episodes:"]
            for ent in eps_list:
                dur = (ent.ended - ent.started) if ent.ended else (time.time() - ent.started)
                lines.append(f"  {humanize_ts(ent.started)} ({humanize_delta(dur)}, {len(ent.events)} events)")
            return Response(text="\n".join(lines), status="EPISODES",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/deadline":
            tokens = arg.strip().split(maxsplit=1)
            if not tokens:
                pend = self.kairos.list_deadlines(only_pending=True)
                if not pend:
                    return Response(text="no pending deadlines", status="DEADLINE",
                                    layer=MemoryLayer.INFERENCE, confidence=0.9)
                lines = ["pending deadlines:"]
                for d in pend:
                    remaining = d.ts - time.time()
                    sign = "in" if remaining > 0 else "overdue by"
                    lines.append(f"  [{d.id}] {d.label} - {sign} {humanize_delta(abs(remaining))}")
                return Response(text="\n".join(lines), status="DEADLINE",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            sub = tokens[0].lower()
            if sub == "add" and len(tokens) > 1:
                parts = tokens[1].split(maxsplit=1)
                if len(parts) < 2:
                    return Response(text="usage: /deadline add <seconds> <label>",
                                    status="USAGE", layer=MemoryLayer.EPHEMERAL, confidence=1.0)
                try:
                    secs = int(parts[0])
                except ValueError:
                    return Response(text="seconds must be integer", status="USAGE",
                                    layer=MemoryLayer.EPHEMERAL, confidence=1.0)
                d = self.kairos.add_deadline(time.time() + secs, parts[1])
                return Response(text=f"deadline added: [{d.id}] {d.label} in {humanize_delta(secs)}",
                                status="DEADLINE_ADD", layer=MemoryLayer.INFERENCE, confidence=0.9)
            if sub == "done" and len(tokens) > 1:
                ok = self.kairos.complete_deadline(tokens[1].strip())
                return Response(text=f"deadline done: {ok}", status="DEADLINE_DONE",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            return Response(text="usage: /deadline [add <secs> <label>|done <id>]",
                            status="USAGE", layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/circadian":
            c = self.kairos.circadian_summary()
            lines = [
                f"total events: {c['total_events']}",
                f"peak hours: {c['peak_hours']}",
                f"quiet hours: {c['quiet_hours']}",
            ]
            return Response(text="\n".join(lines), status="CIRCADIAN",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/today":
            now = datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            events = self.kairos.timeline(start=start, limit=50)
            if not events:
                return Response(text="no events today", status="TODAY",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            lines = [f"today - {len(events)} events:"]
            for ent in events:
                lines.append(f"  [{humanize_ts(ent.ts)}] {ent.kind}: {ent.summary[:80]}")
            return Response(text="\n".join(lines), status="TODAY",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/yesterday":
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            start = today_start - 86400
            events = self.kairos.timeline(start=start, end=today_start, limit=50)
            if not events:
                return Response(text="no events yesterday", status="YESTERDAY",
                                layer=MemoryLayer.INFERENCE, confidence=0.9)
            lines = [f"yesterday - {len(events)} events:"]
            for ent in events:
                lines.append(f"  [{humanize_ts(ent.ts)}] {ent.kind}: {ent.summary[:80]}")
            return Response(text="\n".join(lines), status="YESTERDAY",
                            layer=MemoryLayer.INFERENCE, confidence=0.9)

        if cmd == "/llm":
                    if self.llm is None:
                        return Response(text="llm disabled", status="LLM",
                                        layer=MemoryLayer.EPHEMERAL, confidence=1.0)
                    caps = self.llm.capabilities()
                    lines = [f"{k}: {v}" for k, v in caps.items()]
                    return Response(text="\n".join(lines), status="LLM",
                                    layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        if cmd == "/threshold":
            tokens = (arg or "").strip().split()
            if not tokens:
                lines = ["current thresholds:"]
                for k, v in self.thresholds.items():
                    default = self._threshold_defaults.get(k)
                    marker = "" if abs(v - default) < 1e-9 else f"  (default: {default})"
                    lines.append(f"  {k}: {v}{marker}")
                return Response(text="\n".join(lines), status="THRESHOLD",
                                layer=MemoryLayer.INFERENCE, confidence=1.0)
            action = tokens[0].lower()
            if action == "reset":
                key = tokens[1] if len(tokens) > 1 else None
                ok, msg = self._reset_threshold(key)
                return Response(text=msg, status="THRESHOLD_RESET" if ok else "THRESHOLD_ERROR",
                                layer=MemoryLayer.INFERENCE, confidence=1.0)
            if action == "show":
                return self._handle_command("/threshold")
            key = action
            if len(tokens) < 2:
                return Response(text=f"usage: /threshold {key} <value>", status="USAGE",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            try:
                value = float(tokens[1])
            except ValueError:
                return Response(text=f"value must be a number, got: {tokens[1]}", status="THRESHOLD_ERROR",
                                layer=MemoryLayer.EPHEMERAL, confidence=1.0)
            ok, msg = self._apply_threshold_change(key, value)
            return Response(text=msg, status="THRESHOLD_SET" if ok else "THRESHOLD_ERROR",
                            layer=MemoryLayer.INFERENCE, confidence=1.0)

        if cmd == "/help":
            text = (
                "/remember <text> - store personal note\n"
                "/audit [topic] - list memories\n"
                "/forget <id> - delete memory\n"
                "/correct <id> <text> - supersede memory\n"
                "/promote <id> <layer> - change layer\n"
                "/export - dump memory json\n"
                "/fib <n>, /psi, /wiki <topic>, /weather\n"
                "/peers, /ask <peer> <query>, /read <peer>, /revoke <peer>\n"
                "/exec <flux code>, /mag <json>, /pit, /anomaly <id>\n"
                "/dashboard"
            )
            return Response(text=text, status="HELP",
                            layer=MemoryLayer.EPHEMERAL, confidence=1.0)

        return Response(text=f"unknown command: {cmd}", status="UNKNOWN",
                        layer=MemoryLayer.EPHEMERAL, confidence=1.0)

    def shutdown(self):
        self.running = False
        try:
            if hasattr(self, "mqtt") and self.mqtt is not None and self.mqtt.client is not None:
                self.mqtt.client.disconnect()
                self.mqtt.client.loop_stop()
        except Exception:
            pass


CUSTOM_CSS = """
body { background:#0A0A0F; color:#F0F4FF; font-family: monospace; }
.ohm-box { padding:16px; border:1px solid #2A2A35; border-radius:8px; }
"""


def build_ui(brain: OHMSynapse):
    if not HAS_GRADIO:
        return None

    def chat(msg, history):
        resp = brain.think(msg, origin="local")
        return CitationFormatter.format(resp)

    with gr.Blocks(title=f"OHM-Synapse v{OHM_VERSION}") as demo:
        gr.Markdown(f"# OHM-Synapse v{OHM_VERSION} - Anti-Hallucination Digital Twin")
        gr.Markdown("Type `/help` for commands.")
        gr.ChatInterface(fn=chat)
    return demo


def main():
    brain = OHMSynapse()
    LOG.info(f"OHM-Synapse v{OHM_VERSION} node_id={brain.node_id}")
    demo = build_ui(brain)
    if demo is None:
        LOG.warning("gradio missing, running CLI mode")
        try:
            while True:
                q = input("> ")
                if q.strip() in ("exit", "quit"):
                    break
                r = brain.think(q)
                print(CitationFormatter.format(r))
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            brain.shutdown()
        return
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Base(), css=CUSTOM_CSS)


if __name__ == "__main__":
    main()
