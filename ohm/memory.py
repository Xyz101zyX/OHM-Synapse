import os
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
from ohm.config import OHMConfig
from ohm.security import *
from ohm.crypto import *
from ohm.models import *
from ohm.flux import *
from ohm.fibonacci import *
from ohm.harmonic import *
from ohm.physics import *
from ohm.confidence import *
from ohm.grammar import *


class HoloMem4L:
    def __init__(self, config: "OHMConfig"):
        self.config = config
        self.file_path = config.memory_cfg.get("persistence_file", "./ohm_persistent_memory_v1.json")
        self.inference_ttl = float(config.memory_cfg.get("inference_ttl_seconds", 604800))
        self.store: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.store = json.load(f)
        except Exception:
            self.store = {}
        if "root" not in self.store:
            self.store["root"] = self._make_entry(
                content="genesis",
                layer=MemoryLayer.PERSONAL_RECORD,
                sources=[Source(kind="system", ref="genesis", timestamp=time.time(),
                                detail="initial memory root", layer=MemoryLayer.PERSONAL_RECORD)],
                reliability=1.0,
                user_confirmed=True,
            )
            self._save()
        self._gc()

    def _make_entry(self, content: str, layer: str, sources: List[Source],
                    reliability: float, user_confirmed: bool = False,
                    ttl: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = time.time()
        expires = None
        if layer == MemoryLayer.INFERENCE and ttl is None:
            ttl = self.inference_ttl
        if ttl:
            expires = now + ttl
        return {
            "content": content,
            "layer": layer,
            "sources": [asdict(s) for s in sources],
            "reliability": float(reliability),
            "created": now,
            "updated": now,
            "expires": expires,
            "user_confirmed": bool(user_confirmed),
            "metadata": metadata or {},
            "superseded_by": None,
        }

    def _save(self):
        with self.lock:
            tmp = self.file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.store, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp, self.file_path)

    def _gc(self):
        now = time.time()
        drop = []
        for k, v in self.store.items():
            exp = v.get("expires")
            if exp and exp < now and v.get("layer") == MemoryLayer.INFERENCE:
                drop.append(k)
        for k in drop:
            self.store.pop(k, None)
        if drop:
            self._save()

    def store_memory(self, key: str, content: str, layer: str,
                     sources: Optional[List[Source]] = None,
                     reliability: Optional[float] = None,
                     user_confirmed: bool = False,
                     ttl: Optional[float] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        if layer == MemoryLayer.EPHEMERAL:
            return False
        sources = sources or []
        if layer == MemoryLayer.FACT_EXTERNAL:
            if not sources or not any(s.kind.lower() in ("api", "web", "external", "wikipedia", "http") for s in sources):
                return False
            if reliability is None:
                reliability = 0.9
        elif layer == MemoryLayer.PERSONAL_RECORD:
            if not user_confirmed:
                return False
            if reliability is None:
                reliability = 1.0
        elif layer == MemoryLayer.INFERENCE:
            if not sources:
                return False
            if reliability is None:
                reliability = 0.3
        else:
            return False
        entry = self._make_entry(content, layer, sources, reliability, user_confirmed, ttl, metadata)
        with self.lock:
            self.store[key] = entry
            self._save()
        return True

    def attach_embeddings(self, embedder):
        self._embedder = embedder

    def _get_embedder(self):
        return getattr(self, "_embedder", None)

    def recall_hybrid(self, query: str, top_k: int = 10, embedder=None,
                      keyword_weight: float = 0.4,
                      embedding_weight: float = 0.6) -> List[Dict[str, Any]]:
        self._gc()
        embedder = embedder or self._get_embedder()
        q_words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        q_vec = embedder.embed(query) if (embedder and embedder.available) else None
        layers = MemoryLayer.PERSISTENT
        hits = []
        with self.lock:
            for key, entry in self.store.items():
                if entry.get("layer") not in layers:
                    continue
                if entry.get("superseded_by"):
                    continue
                text = (entry.get("content", "") or "")
                text_lower = text.lower()
                k_score = 0.0
                for w in q_words:
                    if w in key.lower() or w in text_lower:
                        k_score += 1.0
                k_norm = k_score / max(1, len(q_words)) if q_words else 0.0
                e_score = 0.0
                if q_vec is not None:
                    blob = entry.get("embedding", "")
                    e_vec = embedder.decode_storage(blob) if blob else None
                    if e_vec is None:
                        e_vec = embedder.embed(text)
                        if e_vec is not None:
                            entry["embedding"] = embedder.encode_storage(e_vec)
                    e_score = embedder.cosine(q_vec, e_vec)
                if q_vec is not None:
                    hybrid = keyword_weight * k_norm + embedding_weight * e_score
                else:
                    hybrid = k_norm
                if hybrid <= 0.01:
                    continue
                weight = float(entry.get("reliability", 0.5)) ** (1 / Y)
                if entry.get("layer") == MemoryLayer.PERSONAL_RECORD:
                    weight *= 1.15
                hits.append({
                    "id": key,
                    "content": text,
                    "layer": entry.get("layer"),
                    "score": round(hybrid * weight, 4),
                    "hybrid_score": round(hybrid, 4),
                    "keyword_score": round(k_norm, 4),
                    "embedding_score": round(e_score, 4),
                    "sources": entry.get("sources", []),
                    "reliability": entry.get("reliability", 0.5),
                    "created": entry.get("created"),
                })
            self._save()
        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits[:top_k]

    def recall(self, query: str, top_k: int = 5, layers: Optional[Tuple[str, ...]] = None) -> List[Dict[str, Any]]:
        self._gc()
        q_words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        layers = layers or MemoryLayer.PERSISTENT
        hits = []
        with self.lock:
            for key, entry in self.store.items():
                if entry.get("layer") not in layers:
                    continue
                if entry.get("superseded_by"):
                    continue
                text = (entry.get("content", "") or "").lower()
                score = 0.0
                for w in q_words:
                    if w in key.lower() or w in text:
                        score += 1.0
                if score == 0:
                    continue
                norm = score / max(1, len(q_words))
                weight = float(entry.get("reliability", 0.5)) ** (1 / Y)
                if entry.get("layer") == MemoryLayer.PERSONAL_RECORD:
                    weight *= 1.15
                hits.append({
                    "id": key,
                    "content": entry.get("content", ""),
                    "layer": entry.get("layer"),
                    "score": round(norm * weight, 4),
                    "sources": entry.get("sources", []),
                    "reliability": entry.get("reliability", 0.5),
                    "created": entry.get("created"),
                })
        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits[:top_k]

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.store.get(key)

    def forget(self, key: str) -> bool:
        with self.lock:
            if key in self.store:
                self.store.pop(key, None)
                self._save()
                return True
            return False

    def correct(self, key: str, new_content: str, new_layer: str,
                sources: Optional[List[Source]] = None,
                user_confirmed: bool = False) -> bool:
        with self.lock:
            old = self.store.get(key)
            if not old:
                return False
            new_key = f"{key}__v{int(time.time())}"
            ok = self.store_memory(new_key, new_content, new_layer,
                                   sources=sources, user_confirmed=user_confirmed)
            if ok:
                old["superseded_by"] = new_key
                self._save()
            return ok

    def promote(self, key: str, to_layer: str, user_confirmed: bool = False) -> bool:
        with self.lock:
            entry = self.store.get(key)
            if not entry:
                return False
            if to_layer == MemoryLayer.FACT_EXTERNAL:
                if not entry.get("sources"):
                    return False
                entry["layer"] = MemoryLayer.FACT_EXTERNAL
                entry["reliability"] = max(float(entry.get("reliability", 0.3)), 0.9)
            elif to_layer == MemoryLayer.PERSONAL_RECORD:
                if not user_confirmed:
                    return False
                entry["layer"] = MemoryLayer.PERSONAL_RECORD
                entry["reliability"] = 1.0
                entry["user_confirmed"] = True
            else:
                return False
            entry["updated"] = time.time()
            self._save()
            return True

    def audit(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        with self.lock:
            for key, entry in self.store.items():
                if topic and topic.lower() not in key.lower() and topic.lower() not in entry.get("content", "").lower():
                    continue
                out.append({
                    "id": key,
                    "layer": entry.get("layer"),
                    "content": entry.get("content", "")[:200],
                    "sources": entry.get("sources", []),
                    "reliability": entry.get("reliability"),
                    "created": entry.get("created"),
                    "expires": entry.get("expires"),
                    "superseded_by": entry.get("superseded_by"),
                })
        out.sort(key=lambda x: x.get("created") or 0, reverse=True)
        return out

    def export(self) -> Dict[str, Any]:
        with self.lock:
            return deepcopy(self.store)

    def get_delta(self, since: float, layers: Tuple[str, ...] = (MemoryLayer.FACT_EXTERNAL, MemoryLayer.PERSONAL_RECORD)) -> Dict[str, Any]:
        out = {}
        with self.lock:
            for k, v in self.store.items():
                if v.get("layer") in layers and v.get("updated", 0) > since:
                    out[k] = v
        return out

    def apply_delta(self, delta: Dict[str, Any]):
        if not isinstance(delta, dict):
            return
        with self.lock:
            for k, v in delta.items():
                if not isinstance(v, dict):
                    continue
                if v.get("layer") not in (MemoryLayer.FACT_EXTERNAL, MemoryLayer.PERSONAL_RECORD):
                    continue
                self.store[k] = v
            self._save()
