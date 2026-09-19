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
from ohm.confidence import *
from ohm.grammar import *
from ohm.memory import *
from ohm.api import *
from ohm.user_mind import *
from ohm.llm import *
from ohm.mqtt_transport import *
from ohm.config import *


class OhmMiddleware:
    def __init__(self, config: OHMConfig):
        self.cfg = config.middleware_cfg
        self.enabled = self.cfg.get("enabled", True)
        self.threshold = self.cfg.get("threshold", 0.60)
        self.phi = self.cfg.get("golden_ratio", 0.618)
        self.skepticism_threshold = self.cfg.get("skepticism_threshold", 0.3)
        self.patience_cyclic = self.cfg.get("patience_cyclic", True)
        self.auto_recalibrate = self.cfg.get("auto_recalibrate", True)
        self.scheduler = EnergyAwareScheduler()
        self.cycle_phase = 0

    def advance_cycle(self):
        self.cycle_phase += 1

    def get_patience(self) -> float:
        if self.patience_cyclic:
            return 0.5 + 0.5 * math.sin(self.cycle_phase * 0.001)
        return 1.0

    def calculate_importance(self, query: str, memory_hits: List[Dict]) -> float:
        score = 0.0
        if len(query) > 30:
            score += 0.2
        if "?" in query:
            score += 0.1
        if memory_hits and memory_hits[0]["id"] != "root":
            score += 0.5
        if query.startswith(("!", "@", "/")):
            return 1.0
        if any(w in query.lower() for w in ("hi", "hello", "ok")) and len(query) < 20:
            score -= 0.5
        if self.get_patience() < 0.3:
            score *= 0.5
        return max(0.0, min(1.0, score ** (1 / Y)))

    def apply_golden_ratio(self, context_str: str, task_str: str) -> str:
        combined = f"Context: {context_str}\nTask: {task_str}\nResponse:"
        cut = int(len(combined) * self.phi)
        return combined[cut:]

    def recalibrate(self):
        self.cycle_phase = 0
        os.environ[RESISTANCE_KEY] = "0.5"

    def route(self, query: str, memory_hits: List[Dict]) -> Dict[str, Any]:
        if self.enabled:
            ohm_value = float(os.getenv(RESISTANCE_KEY, "0.5"))
            if ohm_value < self.skepticism_threshold:
                if self.auto_recalibrate:
                    self.recalibrate()
                    ohm_value = 0.5
                else:
                    return {"action": "perpetual_skepticism", "reason": f"resistance {ohm_value}"}
            stats = self.scheduler.monitor()
            if stats["ram"] > 95.0 or self.scheduler.get_magnetic_load() > 0.9:
                return {"action": "hardware_guard_active", "reason": f"ram {stats['ram']:.1f}%"}
        importance = self.calculate_importance(query, memory_hits)
        if not self.enabled:
            return {"action": "execute_bypass", "importance": 1.0}
        if importance < self.threshold:
            return {"action": "sleep_mode", "importance": importance,
                    "reason": f"score {importance:.2f} below threshold"}
        mem_text = " ".join(m["content"] for m in memory_hits) if memory_hits else "Empty"
        return {
            "action": "execute_optimized",
            "importance": importance,
            "reason": f"score {importance:.2f}",
            "optimized_prompt": self.apply_golden_ratio(mem_text, query),
        }
