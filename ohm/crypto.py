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


class DeterministicGenesis:
    def __init__(self, signature="xyz101zyx", layer=1):
        self.signature = signature
        self.layer = layer
        self.phi = PHI
        self.x = X
        self.y = Y
        self.z = Z
        self.signature_offset = int(hashlib.sha256(signature.encode()).hexdigest()[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        self.primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
                       59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131]
        self._i = 0
        self._j = 0

    def _vdc(self, index, base):
        v = 0.0
        denom = base
        temp = index
        while denom < 1e6:
            v += (temp % base) / denom
            temp //= base
            if temp == 0:
                break
            denom *= base
        return v % 1.0

    def _next_weight(self):
        u = (self._i * self.phi) % 1.0
        p = self.primes[self._j % len(self.primes)]
        v = self._vdc(self._j, p)
        theta = self.layer * 0.369
        raw = (self.x * u + self.y * v + self.z * theta + self.signature_offset) % 1.0
        w = 2 * (raw ** (1 / self.y)) - 1
        self._j += 1
        if self._j >= 1024:
            self._j = 0
            self._i += 1
        return w

    def urandom(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            w = self._next_weight()
            out.append(max(0, min(255, int(((w + 1) / 2) * 255))))
        return bytes(out)

    def random(self) -> float:
        return (self._next_weight() + 1) / 2

    def randbytes(self, n: int) -> bytes:
        return self.urandom(n)

    def seed(self, *args, **kwargs):
        pass


class GenesisCrypto:
    def __init__(self, signature="xyz101zyx", layer=1):
        self.gen = DeterministicGenesis(signature, layer)

    def encrypt(self, data: dict) -> str:
        pt = json.dumps(data, sort_keys=True).encode()
        ks = self.gen.urandom(len(pt))
        return bytes([p ^ k for p, k in zip(pt, ks)]).hex()

    def decrypt(self, encrypted: str) -> dict:
        ct = bytes.fromhex(encrypted)
        ks = self.gen.urandom(len(ct))
        pt = bytes([c ^ k for c, k in zip(ct, ks)])
        return json.loads(pt.decode())


class GenesisCore:
    def __init__(self, signature: str = "xyz101zyx", layer: int = 1,
                 key_file: str = "./ohm_node_keys.pem"):
        self.signature = signature
        self.layer = layer
        self.key_file = key_file
        self.phi = PHI
        self.gen = DeterministicGenesis(signature, layer)
        self.blacklist: Set[str] = set()
        self.private_key: Any = None
        self.public_key_pem: Optional[bytes] = None
        self.node_id: Optional[str] = None
        self._bootstrap_keys()

    def _bootstrap_keys(self):
        if not HAS_CRYPTO:
            self.node_id = hashlib.sha256(self.signature.encode()).hexdigest()[:16]
            self.public_key_pem = b"NO_CRYPTO"
            return
        key_file = self.key_file
        if not os.path.exists(key_file):
            original_urandom = os.urandom
            os.urandom = self.gen.urandom
            try:
                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            finally:
                os.urandom = original_urandom
            pem_private = private_key.private_bytes(
                encoding=Encoding.PEM, format=PrivateFormat.PKCS8, encryption_algorithm=NoEncryption())
            pem_public = private_key.public_key().public_bytes(
                encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo)
            with open(key_file, "wb") as f:
                f.write(pem_private + pem_public)
        with open(key_file, "rb") as f:
            data = f.read().decode("utf-8")
        priv_match = re.search(r"(-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----)", data, re.DOTALL)
        pub_match = re.search(r"(-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----)", data, re.DOTALL)
        if not priv_match or not pub_match:
            raise ValueError("key file malformed")
        self.private_key = load_pem_private_key(priv_match.group(1).encode(), password=None)
        self.public_key_pem = pub_match.group(1).encode()
        self.node_id = hashlib.sha256(self.public_key_pem).hexdigest()[:16]

    def sign(self, payload: bytes) -> str:
        if not HAS_CRYPTO or self.private_key is None:
            return hashlib.sha256(payload).hexdigest()
        sig = self.private_key.sign(
            payload,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return sig.hex()

    def verify(self, payload: bytes, signature_hex: str, public_key_pem: bytes) -> bool:
        if not HAS_CRYPTO:
            return True
        try:
            pub = load_pem_public_key(public_key_pem)
            if not isinstance(pub, rsa.RSAPublicKey):
                return False
            pub.verify(
                bytes.fromhex(signature_hex), payload,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def sign_query(self, text: str, cycle_limit: int = 9) -> int:
        hash_val = 1
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
                  59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131]
        a, b = 0, 1
        for i, char in enumerate(text.encode() + b"XYZ101ZYX"):
            pk = primes[char % len(primes)]
            if i == 0:
                fk = 0
            elif i == 1:
                fk = 1
            else:
                a, b = b, a + b
                fk = b
            fk_mod = max(1, int((fk ** (1 / Y)) % cycle_limit))
            hash_val = (hash_val * pow(pk, fk_mod, 2 ** 64 - 1)) % (2 ** 64 - 1)
        return hash_val

    def synthesize(self, modules: Dict[str, str], weights: List[float]) -> str:
        total = sum(abs(w) ** Y for w in weights) or 1.0
        norm = [abs(w) ** Y / total for w in weights]
        items = list(modules.items())
        if len(items) != len(norm):
            norm = [1.0 / len(items)] * len(items)
        parts = []
        for (name, value), weight in zip(items, norm):
            if weight > 0.01 and value:
                parts.append(f"[{name}:{weight:.2f}]\n{str(value)[:400]}")
        return "\n\n---\n".join(parts)

    def seal_machine(self, hw_puf: str, sw_hash: str, user_bio: str) -> str:
        h_dna = hashlib.sha256(f"{hw_puf}-{self.signature}".encode()).hexdigest()
        s_dna = hashlib.sha256(f"{sw_hash}-{self.signature}".encode()).hexdigest()
        u_dna = hashlib.sha256(f"{user_bio}-{self.signature}".encode()).hexdigest()
        xor_int = int(h_dna, 16) ^ int(s_dna, 16) ^ int(u_dna, 16)
        alma = hex(xor_int)[2:].zfill(64)
        return bcrypt.hashpw(alma.encode(), bcrypt.gensalt(rounds=10)).decode()
