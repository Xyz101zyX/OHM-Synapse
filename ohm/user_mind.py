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


class MicroUserMind:
    def __init__(self):
        self.profile: Dict[str, Any] = {
            "schemas_used": {},
            "avg_query_length": 0.0,
            "total_queries": 0,
            "cycle_phase": 0,
            "patience_cycles": 0,
        }

    def update(self, query: str, schema_type: Optional[str] = None):
        self.profile["total_queries"] += 1
        q_len = len(query)
        self.profile["avg_query_length"] = (
            (self.profile["avg_query_length"] * (self.profile["total_queries"] - 1) + q_len)
            / self.profile["total_queries"]
        )
        if schema_type:
            self.profile["schemas_used"][schema_type] = self.profile["schemas_used"].get(schema_type, 0) + 1

    def advance_cycle(self):
        self.profile["cycle_phase"] += 1
        if self.profile["cycle_phase"] % 1000 == 0:
            self.profile["patience_cycles"] += 1
            self.profile["cycle_phase"] = 0

    def get_profile(self) -> str:
        sorted_schemas = sorted(self.profile["schemas_used"].items(), key=lambda x: x[1], reverse=True)
        top = sorted_schemas[0][0] if sorted_schemas else "None"
        return json.dumps({
            "top_domain": top,
            "avg_cognitive_load": f"{self.profile['avg_query_length']:.1f}",
            "phase": self.profile["cycle_phase"],
        })


class SignalAwareness:
    def __init__(self):
        self.current_state: Dict[str, Any] = {
            "effective_type": "4g",
            "downlink": 10.0,
            "rtt": 50,
            "presence": True,
            "motion": "static",
            "last_update": time.time(),
        }

    def update_from_network_api(self, info: Dict[str, Any]):
        self.current_state.update(info)
        self.current_state["last_update"] = time.time()

    def update_from_wifi_sensing(self, csi: Dict[str, Any]):
        self.current_state.update(csi)
        self.current_state["last_update"] = time.time()

    def get_adaptation_policy(self) -> Dict[str, Any]:
        policy = {"use_llm": True, "use_external_search": True, "verbosity": "normal", "energy_mode": "balanced"}
        if self.current_state.get("effective_type") in ("slow-2g", "2g"):
            policy.update({"use_llm": False, "energy_mode": "low"})
        rtt_val = self.current_state.get("rtt", 0)
        try:
            rtt_num = int(rtt_val) if rtt_val is not None else 0
        except (TypeError, ValueError):
            rtt_num = 0
        if rtt_num > 200:
            policy["energy_mode"] = "low"
        if not self.current_state.get("presence", True):
            policy.update({"energy_mode": "hibernate", "use_llm": False})
        return policy


class ContextualCollector:
    @classmethod
    def collect_all(cls) -> Dict[str, Any]:
        try:
            geo = cls.get_geolocation()
            net = cls.get_network_quality()
            try:
                w = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={"latitude": -23.55, "longitude": -46.63, "current_weather": True},
                    timeout=2,
                ).json().get("current_weather", {})
            except Exception:
                w = {"temperature": "N/A", "windspeed": "N/A"}
        except Exception:
            geo = {"isp": "localhost", "city": "localhost", "ip": "127.0.0.1"}
            net = {"latency_ms": "0", "quality": "localhost"}
            w = {"temperature": "N/A", "windspeed": "N/A"}
        return {"weather": w, "geolocation": geo, "network": net,
                "timestamp": datetime.now().isoformat()}

    @staticmethod
    def get_network_quality() -> Dict[str, str]:
        try:
            start = time.time()
            requests.get("https://www.google.com", timeout=2)
            latency = (time.time() - start) * 1000
            quality = "excellent" if latency < 100 else "good" if latency < 300 else "poor"
            return {"latency_ms": f"{latency:.0f}", "quality": quality}
        except Exception:
            return {"latency_ms": "0", "quality": "localhost"}

    @staticmethod
    def get_geolocation() -> Dict[str, str]:
        try:
            r = requests.get("https://ipinfo.io/json", timeout=3).json()
            return {"isp": r.get("org", "N/A"), "city": r.get("city", "N/A"), "ip": r.get("ip", "N/A")}
        except Exception:
            return {"isp": "localhost", "city": "localhost", "ip": "127.0.0.1"}
