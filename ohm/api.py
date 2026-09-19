import os
import urllib.parse as _urlparse
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


class PublicAPIManager:
    headers = {"User-Agent": f"OHM-Synapse/{OHM_VERSION}"}

    def __init__(self, config: Optional[Dict[str, str]] = None):
        self.config = config or {}
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._cache_ttl = 300

    def _request(self, url: str, params: Optional[Dict] = None,
                 headers: Optional[Dict] = None, max_retries: int = 2) -> Optional[Dict[str, Any]]:
        headers = headers or {}
        headers.setdefault("User-Agent", self.headers["User-Agent"])
        key = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        cached = self._cache.get(key)
        if cached and time.time() - cached[1] < self._cache_ttl:
            return cached[0]
        for attempt in range(max_retries + 1):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    self._cache[key] = (data, time.time())
                    return data
                if r.status_code == 429 and attempt < max_retries:
                    time.sleep(1.5 ** attempt)
                    continue
                return {"error": f"status {r.status_code}"}
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                return {"error": str(e)}
        return {"error": "max retries"}

    def get_weather_openmeteo(self, lat: float = -23.55, lon: float = -46.63) -> Dict:
        return self._request(
            "https://api.open-meteo.com/v1/forecast",
            {"latitude": lat, "longitude": lon, "current_weather": True, "timezone": "auto"},
        ) or {}

    def get_geolocation_ipinfo(self, ip: Optional[str] = None) -> Dict:
        url = "https://ipinfo.io/json" if not ip else f"https://ipinfo.io/{ip}/json"
        return self._request(url) or {}

    def get_wikipedia_summary(self, query: str) -> Dict:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + _urlparse.quote(query)
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            fallback = (f"https://en.wikipedia.org/w/api.php?action=query&format=json"
                        f"&prop=extracts&exintro&explaintext&titles={_urlparse.quote(query)}")
            r2 = requests.get(fallback, headers=self.headers, timeout=10)
            if r2.status_code == 200:
                data = r2.json()
                for _, pd in data.get("query", {}).get("pages", {}).items():
                    if "extract" in pd:
                        return {"extract": pd["extract"], "source_url": fallback}
            return {"error": f"status {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def search_wikipedia(self, query: str) -> Optional[Dict]:
        try:
            url = (f"https://en.wikipedia.org/w/api.php?action=query&format=json"
                   f"&list=search&srsearch={_urlparse.quote(query)}")
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                results = r.json().get("query", {}).get("search", [])
                if results:
                    return self.get_wikipedia_summary(results[0]["title"])
        except Exception:
            pass
        return None

    def get_restcountries(self, country: Optional[str] = None) -> Dict:
        url = f"https://restcountries.com/v3.1/name/{country}" if country else "https://restcountries.com/v3.1/all"
        return self._request(url) or {}
