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


class FibonacciModule:
    def __init__(self):
        self.cache: Dict[int, int] = {0: 0, 1: 1}
        self.pisano_cache: Dict[int, int] = {}

    def fib(self, n: int) -> int:
        if n in self.cache:
            return self.cache[n]
        if n < 0:
            raise ValueError("n must be >= 0")
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        self.cache[n] = b
        return b

    def is_prime(self, n: int) -> bool:
        if n < 2:
            return False
        if n % 2 == 0:
            return n == 2
        i = 3
        while i * i <= n:
            if n % i == 0:
                return False
            i += 2
        return True

    def fibonacci_prime_check(self, n: int) -> Dict[str, Any]:
        value = self.fib(n)
        return {
            "n": n,
            "F(n)": value,
            "n_is_prime": self.is_prime(n),
            "F(n)_is_prime": self.is_prime(value),
        }

    def pisano_period(self, p: int) -> int:
        if p in self.pisano_cache:
            return self.pisano_cache[p]
        if p == 2:
            return 3
        if p == 5:
            return 20
        a, b = 0, 1
        for i in range(p * p + 1):
            a, b = b, (a + b) % p
            if a == 0 and b == 1:
                self.pisano_cache[p] = i + 1
                return i + 1
        self.pisano_cache[p] = -1
        return -1
