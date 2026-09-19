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
from ohm.middleware import *


class GreekFramework:
    def __init__(self, alfa, beta_func, gama=3, delta_func=lambda x, y: abs(x - y),
                 epsilon=5, zeta_func=None, eta=0.01, theta=1.0, lam=1.0,
                 mu=None, sigma=1.0, omega=0.0):
        self.alpha = alfa
        self.beta = beta_func
        self.gamma = gama
        self.delta = delta_func
        self.epsilon = epsilon
        self.zeta = zeta_func or (lambda x: x)
        self.eta = eta
        self.theta = theta
        self.lam = lam
        self.mu = mu
        self.sigma = sigma
        self.omega = omega

    def calculate_psi(self) -> float:
        if not HAS_NUMPY:
            return 0.0
        if not self.alpha or len(self.alpha[0]) < 3:
            return 0.0
        arr = np.array(self.alpha[0], dtype=float)
        norm = (arr - arr.mean()) / (arr.std() + 1e-9)
        n = (len(norm) // self.gamma) * self.gamma
        if n == 0:
            return 0.0
        psi = 0.0
        for k in range(0, n, self.gamma):
            x, y, z = norm[k], norm[k + 1], norm[k + 2]
            psi += (self.lam * self.delta(x, y) * z) ** self.epsilon
        psi_agg = psi / max(1, n // self.gamma)
        residual = self.omega * self.theta
        return float(psi_agg + residual)

    def update_alpha(self, novos):
        self.alpha = novos


class ToMAgent(GreekFramework):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.belief_about_other: Dict[str, Any] = {}
        self.prediction = None

    def simulate_mind(self, observed_action) -> Tuple[float, float]:
        if not HAS_NUMPY:
            return 0.0, 0.0
        perception = float(np.mean(observed_action))
        prev = self.belief_about_other.get("state", 0.0)
        err = abs(self.prediction - perception) if self.prediction is not None else 0.0
        self.belief_about_other["state"] = prev * (1 - self.eta) + self.eta * err
        self.prediction = perception
        return self.calculate_psi(), self.omega

    def get_beliefs(self) -> Dict[str, Any]:
        return {
            "state": self.belief_about_other.get("state", 0.0),
            "prediction": self.prediction,
            "omega": self.omega,
        }
