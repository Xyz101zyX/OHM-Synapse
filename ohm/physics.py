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


class MagneticFieldModule:
    def __init__(self):
        self.mu0 = 4 * math.pi * 1e-7

    def field_from_wire(self, point: List[float], current: float,
                        start: List[float], end: List[float]) -> List[float]:
        if not HAS_NUMPY:
            return [0.0, 0.0, 0.0]
        p, a, b = np.array(point), np.array(start), np.array(end)
        r1, r2 = p - a, p - b
        r1m, r2m = np.linalg.norm(r1), np.linalg.norm(r2)
        if r1m < 1e-12 or r2m < 1e-12:
            return [0.0, 0.0, 0.0]
        dl = b - a
        B = (self.mu0 * current / (4 * math.pi)) * (
            np.cross(dl, r1) / (r1m ** 3) - np.cross(dl, r2) / (r2m ** 3))
        return B.tolist()

    def field_map(self, points: List[List[float]], sources: Dict[str, Any]) -> Dict[str, Any]:
        if not HAS_NUMPY:
            return {"error": "numpy required"}
        B_total = np.zeros((len(points), 3))
        for wire in sources.get("wires", []):
            for i, p in enumerate(points):
                B_total[i] += np.array(self.field_from_wire(
                    p, wire.get("current", 1.0),
                    wire.get("start", [-1, 0, 0]), wire.get("end", [1, 0, 0])))
        return {"B_mag": np.linalg.norm(B_total, axis=1).tolist()}


class PiTEngine:
    def __init__(self):
        self.g0 = 9.80665
        self.isp_s = 5000
        self.m_dot = 0.001

    def get_status(self) -> Dict[str, Any]:
        thrust = self.m_dot * self.g0 * self.isp_s
        return {"isp_s": self.isp_s, "thrust_N": thrust,
                "exhaust_velocity_m_s": self.isp_s * self.g0}


class AnomalyAnalyzer:
    def __init__(self):
        self.anomalies = {
            1: {"title": "Retrograde Orbit", "desc": "reversed trajectory"},
            2: {"title": "Hill Sphere Pass", "desc": "gravitational limit"},
            3: {"title": "Solar Occultation", "desc": "hidden behind sun"},
        }

    def get_anomaly(self, aid: int) -> Dict[str, Any]:
        return self.anomalies.get(aid, {"title": "unknown", "desc": "n/a"})
