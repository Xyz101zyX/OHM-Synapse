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


X = 3.0


Y = 13.8


Z = 9.0


PHI = 1.618033988749895


TRIAD = 13.8


TRIAD_INV = 1.0 / TRIAD


OHM_VERSION = "0.0.1"


ABSTAIN_MARKERS = (
    "i do not have that information",
    "i don't have that information",
    "i do not have any information",
    "i don't have any information",
    "no information available",
    "insufficient information",
    "i cannot answer",
    "i can't answer",
    # expansions for LLM phrasings observed in v3 benchmark
    "i do not have",
    "i don't have",
    "i do not know",
    "i don't know",
    "i am unable to",
    "i'm unable to",
    "unable to determine",
    "cannot determine",
    "can't determine",
    "not able to determine",
    "unable to provide",
    "cannot provide",
    "i have no information",
    "i have no knowledge",
    "no knowledge",
    "not enough information",
    "without more information",
    "i am not sure",
    "i'm not sure",
    "i am not able",
    "i'm not able",
)


RESISTANCE_KEY = "OHM_RESISTANCE"


os.environ[RESISTANCE_KEY] = "0.5"


LOG = logging.getLogger("ohm")


LOG.setLevel(logging.INFO)


if not LOG.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    LOG.addHandler(_h)


class MemoryLayer:
    FACT_EXTERNAL = "FACT_EXTERNAL"
    PERSONAL_RECORD = "PERSONAL_RECORD"
    INFERENCE = "INFERENCE"
    EPHEMERAL = "EPHEMERAL"
    ALL = (FACT_EXTERNAL, PERSONAL_RECORD, INFERENCE, EPHEMERAL)
    PERSISTENT = (FACT_EXTERNAL, PERSONAL_RECORD, INFERENCE)


def infer_archetype(text: str) -> str:
    text_lower = text.lower()
    scores = {letter: 0 for letter in ARCHETYPE_LETTERS}
    for letter, keywords in ARCHETYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[letter] += 1
    best = max(scores, key=lambda k: (scores[k], -ord(k)))
    return best if scores[best] > 0 else "A"


def calculate_archetype_weights() -> Dict[str, float]:
    weights = {}
    for i, letter in enumerate(ARCHETYPE_LETTERS):
        n = i
        raw = ((X * (n + 1) ** PHI) + (Y * ((n * 7) % 37) / 37.0) + (Z * math.sin(n * PHI))) % 1.0
        scaled = 1.0 / (1.0 + math.exp(-10 * (raw - 0.5)))
        weights[letter] = round(0.15 + 0.70 * scaled, 4)
    return weights


OHM_SYNAPSE_YAML = f"""
version: {OHM_VERSION}
triad:
  x: {X}
  y: {Y}
  z: {Z}
runtime:
  environment: production
  hot_reload: false
  log_level: info
sovereign:
  identity: OHM-Synapse
  mode: autonomous
  auto_adapt: true
  cognitive_profile: true
memory:
  persistence_file: ./ohm_persistent_memory_v1.json
  audit_file: ./ohm_audit_v1.jsonl
  export_file: ./ohm_memory_export.json
  holographic_consolidation:
    auto_defrag: true
    resonance_threshold: 0.72
  inference_ttl_seconds: 604800
cognition:
  meta_recursion:
    enabled: true
    log2_depth_limit: true
    patience_cyclic: true
  energy_aware:
    enabled: true
    low_power_mode_threshold: 80.0
  thresholds:
    grounding: 0.20
    confidence_respond: 0.80
    confidence_caution: 0.50
llm_adapter:
  enabled: true
  provider: ollama
  endpoint: http://localhost:11434
  model_name: llama3.2:1b
  timeout: 30
  api_key_env: ""
  max_tokens: 1024
  fallback: symbolic_mode
ohm_middleware:
  enabled: true
  threshold: 0.60
  golden_ratio: 0.618
  skepticism_threshold: 0.3
  patience_cyclic: true
  auto_recalibrate: true
confidence:
  weights:
    source_score: 0.35
    coverage: 0.25
    consistency: 0.20
    residual: 0.10
    llm_penalty: 0.30
  thresholds:
    respond: 0.80
    caution: 0.50
security:
  allow_public_broker: false
  require_tls: true
  max_exec_per_minute: 20
  max_queries_per_minute: 60
distributed:
  enabled: true
  mqtt_broker: localhost
  mqtt_port: 8883
  sync_interval: 30
  delta_sync: true
  secure_delta: true
  mqtt_user: ""
  mqtt_password: ""
  sync_layers:
    - FACT_EXTERNAL
    - PERSONAL_RECORD
modules:
  fibonacci: true
  harmonizer: true
  magnetic_sim: true
  pit_engine: true
  anomaly_analyzer: true
  flux_engine: true
api_manager:
  enabled: true
  timeout: 10
  cache_ttl: 300
greek_framework:
  enabled: true
  gamma: 3
  epsilon: 5
  eta: 0.01
  theta: 0.5
  lam: 1.0
  omega: 0.1
"""


ARCHETYPE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUV"


ARCHETYPE_NAMES = [
    "Phi", "Golden Ratio", "Fibonacci Spiral", "Lucas Number", "Golden Angle",
    "Fibonacci Sequence", "Binets Formula", "Golden Rectangle", "Fibonacci Tiling",
    "Golden Section", "Fibonacci Prime", "Pisano Period", "Fibonacci Word",
    "Golden Triangle", "Fibonacci Number", "Lucas Sequence", "Zeckendorf Rep",
    "Golden Spiral", "Fibbinary", "Fibonacci Coding", "Golden Rhombus", "Fibonacci Heap"
]


ARCHETYPE_KEYWORDS = {
    "A": ["creativity", "beginning", "leap", "risk", "new", "start", "potential", "spontaneous"],
    "B": ["power", "will", "realize", "tool", "action", "skill", "create", "influence"],
    "C": ["intuition", "mystery", "subconscious", "dream", "silence", "sensitivity"],
    "D": ["nature", "abundance", "fertility", "mother", "growth", "nourish", "flourish"],
    "E": ["structure", "authority", "order", "leadership", "government", "rule"],
    "F": ["tradition", "teaching", "wisdom", "ritual", "religion", "knowledge", "mentor"],
    "G": ["love", "relationship", "choice", "harmony", "partner", "decision", "balance"],
    "H": ["determination", "victory", "movement", "direction", "control", "challenge"],
    "I": ["courage", "strength", "patience", "mastery", "instinct", "persistence"],
    "J": ["solitude", "search", "introspection", "truth", "guide", "inner wisdom"],
    "K": ["luck", "cycle", "destiny", "change", "chance", "revolution", "opportunity"],
    "L": ["justice", "truth", "balance", "law", "causality", "consequence"],
    "M": ["surrender", "sacrifice", "new perspective", "pause"],
    "N": ["transformation", "renewal", "end", "beginning", "detachment", "metamorphosis"],
    "O": ["healing", "balance", "mixture", "alchemy", "integration", "transmutation"],
    "P": ["materiality", "illusion", "overcoming", "desire", "shadow", "liberation"],
    "Q": ["rupture", "sudden truth", "collapse", "revelation", "fall", "awakening"],
    "R": ["hope", "inspiration", "healing", "renewal", "guide", "peace"],
    "S": ["fear", "illusion", "darkness", "mystery", "confusion"],
    "T": ["clarity", "joy", "success", "energy", "light", "realization"],
    "U": ["reflection", "calling", "awakening", "forgiveness", "review", "new cycle"],
    "V": ["totality", "integration", "completeness", "realization", "unity", "fullness"]
}


ARCHETYPE_WEIGHTS = calculate_archetype_weights()

