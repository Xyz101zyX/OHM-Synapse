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


class SymbolicResolver:
    def __init__(self):
        self.rules: Dict[str, list] = {"if_then": []}

    def evaluate(self, expression: str) -> str:
        expr_lower = expression.lower()
        if "calculate" in expr_lower:
            try:
                tail = expr_lower.split("calculate", 1)[1].strip()
                allowed = set("0123456789+-*/(). ")
                if not set(tail) <= allowed:
                    return "symbolic_error: unsafe expression"
                return f"symbolic: {eval(tail, {'__builtins__': {}}, {})}"
            except Exception as e:
                return f"symbolic_error: {e}"
        return "no symbolic rule"

    def learn_rule(self, if_c: str, then_c: str) -> str:
        self.rules["if_then"].append({"if": if_c.lower(), "then": then_c.lower()})
        return f"rule learned: IF {if_c} THEN {then_c}"


class StructuralGrammar:
    def __init__(self):
        self.schema = {
            "Fact": {"required": ["statement", "source_url", "source_kind"]},
            "PersonalNote": {"required": ["statement", "user_confirmed"]},
            "Inference": {"required": ["statement", "derived_from"]},
            "Experiment": {"required": ["conditions", "result", "date"]},
            "Hypothesis": {"required": ["statement", "evidences"]},
        }

    def validate(self, note: Dict[str, Any]) -> Tuple[bool, str]:
        if not isinstance(note, dict):
            return False, "not_a_dict"
        tipo = note.get("type")
        if tipo not in self.schema:
            return False, "unknown_type"
        for f in self.schema[tipo]["required"]:
            val = note.get(f)
            if val is None:
                return False, f"missing_{f}"
            if isinstance(val, str) and val.strip().lower() in ("", "none", "n/a", "empty"):
                return False, f"empty_{f}"
            if tipo == "PersonalNote" and f == "user_confirmed" and not val:
                return False, "not_confirmed"
        return True, "ok"


class ConfluenceVerifier:
    def __init__(self):
        self.rules: List[Tuple[str, Any, str, Any]] = []

    def add_rule(self, f_cond: str, v_cond: Any, f_targ: str, v_targ: Any):
        self.rules.append((f_cond, v_cond, f_targ, v_targ))

    def check(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        conflicts = []
        for note in notes:
            for f_cond, v_cond, f_targ, v_targ in self.rules:
                if note.get(f_cond) == v_cond and note.get(f_targ) != v_targ:
                    conflicts.append({
                        "id": note.get("id", "?"),
                        "broken_rule": f"{f_cond}={v_cond} requires {f_targ}={v_targ}",
                    })
        return conflicts

    def check_pair(self, a: Dict[str, Any], b: Dict[str, Any]) -> Optional[str]:
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        if a.get("type") == b.get("type") == "Fact":
            if a.get("statement") and b.get("statement"):
                if a["statement"].strip().lower() != b["statement"].strip().lower():
                    if a.get("subject") and b.get("subject") and a["subject"] == b["subject"]:
                        return f"conflict on subject {a['subject']}"
        return None
