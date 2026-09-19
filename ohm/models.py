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


@dataclass
class Source:
    kind: str
    ref: str
    timestamp: float
    detail: str = ""
    layer: str = MemoryLayer.FACT_EXTERNAL


@dataclass
class Response:
    text: str
    status: str
    layer: str
    confidence: float
    sources: List[Source] = field(default_factory=list)
    verifications: Dict[str, Any] = field(default_factory=dict)
    llm_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class CitationFormatter:
    @staticmethod
    def format(resp: Response) -> str:
        lines = []
        lines.append("RESPONSE")
        lines.append("  " + (resp.text or "").replace("\n", "\n  "))
        lines.append("")
        lines.append("SOURCES")
        if not resp.sources:
            lines.append("  [none]")
        else:
            for i, s in enumerate(resp.sources, 1):
                ts = datetime.fromtimestamp(s.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"  [F{i}] {s.kind} | {s.ref} | {ts}")
                if s.detail:
                    lines.append(f"       {s.detail}")
        lines.append("")
        lines.append("CONFIDENCE")
        lines.append(f"  score={resp.confidence:.3f} layer={resp.layer} status={resp.status} llm={resp.llm_used}")
        if resp.verifications:
            v = " ".join(f"{k}={val}" for k, val in resp.verifications.items())
            lines.append(f"  checks: {v}")
        return "\n".join(lines)


class AuditLog:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Dict[str, Any], signer: Optional[Callable[[bytes], str]] = None):
        entry = dict(event)
        entry["timestamp"] = time.time()
        payload = json.dumps(entry, sort_keys=True).encode()
        if signer is not None:
            entry["signature"] = signer(payload)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        out: deque = deque(maxlen=n)
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return list(out)
