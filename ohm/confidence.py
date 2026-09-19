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
from ohm.security import *
from ohm.crypto import *
from ohm.models import *
from ohm.flux import *
from ohm.fibonacci import *
from ohm.harmonic import *
from ohm.physics import *


class ConfidenceScorer:
    STOPWORDS = {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "the", "and", "or", "but", "for", "with", "without", "from", "into",
        "this", "that", "these", "those", "there", "here", "some", "any", "all",
        "are", "was", "were", "been", "being", "have", "has", "had", "does", "did",
        "will", "would", "should", "could", "can", "may", "might", "must",
        "your", "yours", "their", "theirs", "our", "ours", "its",
    }
    def __init__(self, cfg: Dict[str, Any]):
        w = cfg.get("weights", {})
        self.w_source = float(w.get("source_score", 0.35))
        self.w_coverage = float(w.get("coverage", 0.25))
        self.w_consistency = float(w.get("consistency", 0.20))
        self.w_residual = float(w.get("residual", 0.10))
        self.w_penalty = float(w.get("llm_penalty", 0.30))
        t = cfg.get("thresholds", {})
        self.t_respond = float(t.get("respond", 0.80))
        self.t_caution = float(t.get("caution", 0.50))

    def _source_score(self, sources: List[Source]) -> float:
        if not sources:
            return 0.0
        best = 0.0
        for s in sources:
            kind = (s.kind or "").lower()
            if kind == "llm-general":
                v = 0.85
            elif kind == "llm":
                v = 0.5
            elif s.layer == MemoryLayer.PERSONAL_RECORD:
                v = 1.0
            elif s.layer == MemoryLayer.FACT_EXTERNAL:
                v = 0.9 if ("wikipedia" in s.ref.lower() or "gov" in s.ref.lower()) else 0.7
            elif s.layer == MemoryLayer.INFERENCE:
                v = 0.4
            else:
                v = 0.1
            if v > best:
                best = v
        return best

    def _coverage(self, query: str, memories: List[Dict[str, Any]],
                  sources: Optional[List[Source]] = None) -> float:
        if not query:
            return 0.0
        q_all = set(w for w in re.findall(r"\w+", query.lower()) if len(w) > 2)
        if not q_all:
            return 0.0
        q_content = {w for w in q_all if w not in self.STOPWORDS}
        q_tokens = q_content if q_content else q_all
        covered = set()
        texts = [(m.get("content", "") or "") for m in memories]
        if sources:
            for s in sources:
                texts.append((s.detail or "") + " " + (s.ref or ""))
        for text in texts:
            text_lower = text.lower()
            for t in q_tokens:
                if t in text_lower:
                    covered.add(t)
        return len(covered) / len(q_tokens)
        
    def _consistency(self, verifications: Dict[str, Any]) -> float:
        grammar_ok = verifications.get("grammar_ok", True)
        confluence_ok = verifications.get("confluence_ok", True)
        grounding_ok = verifications.get("grounding_ok", True)
        score = 0.0
        if grammar_ok:
            score += 0.34
        if confluence_ok:
            score += 0.33
        if grounding_ok:
            score += 0.33
        return score

    def _residual(self, verifications: Dict[str, Any]) -> float:
        return float(verifications.get("residual", 0.0))

    def score(self, query: str, memories: List[Dict[str, Any]],
              sources: List[Source], verifications: Dict[str, Any],
              llm_used: bool) -> float:
        s_src = self._source_score(sources)
        s_cov = self._coverage(query, memories, sources)
        s_con = self._consistency(verifications)
        s_res = 1.0 - self._residual(verifications)
        penalty = self.w_penalty if llm_used and not sources else 0.0
        raw = (self.w_source * s_src
               + self.w_coverage * s_cov
               + self.w_consistency * s_con
               + self.w_residual * s_res
               - penalty)
        return max(0.0, min(1.0, raw))

    def decision(self, conf: float) -> str:
        if conf >= self.t_respond:
            return "respond"
        if conf >= self.t_caution:
            return "caution"
        return "abstain"
