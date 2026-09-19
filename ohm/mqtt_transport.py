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


class MQTTClient:
    def __init__(self, broker: str, port: int, client_id: str,
                 msg_queue: Optional[queue.Queue], security_cfg: Dict[str, Any]):
        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.msg_queue = msg_queue
        self.security_cfg = security_cfg or {}
        self.client = None
        self.enabled = False
        if not HAS_MQTT:
            LOG.warning("paho-mqtt missing")
            return
        if self.broker in ("broker.hivemq.com", "test.mosquitto.org", "broker.emqx.io") \
                and not self.security_cfg.get("allow_public_broker", False):
            LOG.warning("public broker rejected by security policy")
            return
        try:
            try:
                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
            except Exception:
                self.client = mqtt.Client(client_id=self.client_id)
            if self.msg_queue:
                self.client.on_message = self._on_message
            if self.security_cfg.get("require_tls", True):
                try:
                    self.client.tls_set()
                    self.client.tls_insecure_set(True)
                except Exception as e:
                    LOG.warning(f"TLS setup failed: {e}")
            user = self.security_cfg.get("mqtt_user") or ""
            password = self.security_cfg.get("mqtt_password") or ""
            if user:
                self.client.username_pw_set(user, password)
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            if self.msg_queue:
                self.client.subscribe("ohm/network/#")
                self.client.subscribe("ohm/delta/#")
                self.client.subscribe("ohm/revoke/#")
            self.enabled = True
            LOG.info(f"MQTT connected {self.broker}:{self.port}")
        except Exception as e:
            LOG.warning(f"MQTT connection failed: {e}")
            self.client = None
            self.enabled = False

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except Exception:
            payload = {"raw": message.payload.decode("utf-8", errors="replace")}
        if self.msg_queue is not None:
            self.msg_queue.put({"topic": message.topic, "payload": payload})

    def publish(self, topic: str, payload: Dict[str, Any], qos: int = 1):
        if self.client is None or not self.enabled:
            return
        try:
            self.client.publish(topic, json.dumps(payload, default=str), qos=qos)
        except Exception as e:
            LOG.warning(f"publish failed: {e}")


class InterAgentHarmonizer:
    def __init__(self, ohm):
        self.ohm = ohm
        self.mappings: Dict[Tuple[str, str], Dict[str, str]] = {}
        self.agent_profiles: Dict[str, Dict[str, Any]] = {}

    def discover_agent(self, agent_id: str, sample_input: str, sample_output: str) -> str:
        self.agent_profiles[agent_id] = {"last_seen": time.time()}
        return f"agent {agent_id} discovered"

    def link_agents(self, a: str, b: str) -> str:
        self.mappings[(a, b)] = {"input": "query", "output": "response"}
        self.mappings[(b, a)] = {"query": "input", "response": "output"}
        return f"linked {a}<->{b}"

    def translate(self, agent_from: str, agent_to: str, message: Dict[str, Any]) -> Dict[str, Any]:
        mapping = self.mappings.get((agent_from, agent_to), {"input": "prompt"})
        return {to_f: message[from_f] for from_f, to_f in mapping.items() if from_f in message}
