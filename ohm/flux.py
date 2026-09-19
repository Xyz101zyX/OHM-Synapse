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


class FluxArena:
    def __init__(self, size: int = 16 * 1024 * 1024):
        self.size = size
        self.mem = bytearray(size)
        self.ptr = 0

    def alloc(self, n: int) -> int:
        if self.ptr + n > self.size:
            self.reset()
        addr = self.ptr
        self.ptr += n
        return addr

    def reset(self):
        self.ptr = 0

    def write(self, addr: int, data: bytes):
        self.mem[addr:addr + len(data)] = data

    def read(self, addr: int, n: int) -> bytes:
        return bytes(self.mem[addr:addr + n])


class FluxCompiler:
    def __init__(self):
        self.registers = {'RAX': 0, 'RBX': 1, 'RCX': 2, 'RDX': 3, 'RDI': 4, 'RSI': 5, 'RBP': 6, 'RSP': 7}
        self.labels = {}
        self.output = bytearray()
        self.current_pos = 0

    def compile(self, flux_code: str) -> bytes:
        lines = [l.strip() for l in flux_code.strip().split('\n') if l.strip()]
        self.labels = {}
        self.output = bytearray()
        self.current_pos = 0
        for line in lines:
            if line.startswith(':'):
                self.labels[line[1:]] = self.current_pos
            else:
                self.current_pos += 10
        self.current_pos = 0
        for line in lines:
            if line.startswith(':'):
                continue
            if line.startswith('START'):
                continue
            self._emit(line)
        return bytes(self.output)

    def _emit(self, line: str):
        parts = line.replace(',', ' ').split()
        if not parts:
            return
        op = parts[0].upper()
        handler = getattr(self, f"_op_{op.lower()}", None)
        if handler is None:
            raise ValueError(f"Unknown instruction: {op}")
        handler(parts[1:])

    def _op_mov(self, args):
        dest, src = args[0], args[1]
        val = int(src, 16) if src.startswith('0x') else int(src)
        self.output.extend([0x48, 0xB8])
        self.output.extend(struct.pack('<Q', val & 0xFFFFFFFFFFFFFFFF))
        if dest.upper() != 'RAX':
            self.output.extend([0x48, 0x89, 0xC0 + self.registers.get(dest.upper(), 0)])

    def _op_add(self, args):
        self._emit_alu('ADD', args[0], args[1])

    def _op_sub(self, args):
        self._emit_alu('SUB', args[0], args[1])

    def _emit_alu(self, op, dest, src):
        if src.startswith('0x') or src.lstrip('-').isdigit():
            val = int(src, 16) if src.startswith('0x') else int(src)
            self.output.extend([0x48, 0x81, (0xC0 if op == 'ADD' else 0xE8) + self.registers.get(dest.upper(), 0)])
            self.output.extend(struct.pack('<I', val & 0xFFFFFFFF))
        else:
            self.output.extend([0x48, 0x01 if op == 'ADD' else 0x29,
                                0xC0 + self.registers.get(dest.upper(), 0) + (self.registers.get(src.upper(), 0) << 3)])

    def _op_mul(self, args):
        self.output.extend([0x48, 0xF7, 0xE0 + self.registers.get(args[0].upper(), 0)])

    def _op_div(self, args):
        self.output.extend([0x48, 0xF7, 0xF0 + self.registers.get(args[0].upper(), 0)])

    def _op_cmp(self, args):
        a, b = args[0], args[1]
        if b.startswith('0x') or b.lstrip('-').isdigit():
            val = int(b, 16) if b.startswith('0x') else int(b)
            self.output.extend([0x48, 0x81, 0xF8 + self.registers.get(a.upper(), 0)])
            self.output.extend(struct.pack('<I', val & 0xFFFFFFFF))
        else:
            self.output.extend([0x48, 0x39, 0xC0 + self.registers.get(a.upper(), 0) + (self.registers.get(b.upper(), 0) << 3)])

    def _op_jmp(self, args):
        offset = self.labels.get(args[0], 0) - (self.current_pos + 5)
        self.output.extend([0xE9])
        self.output.extend(struct.pack('<I', offset & 0xFFFFFFFF))

    def _cond_jmp(self, op1, op2, label):
        offset = self.labels.get(label, 0) - (self.current_pos + 6)
        self.output.extend([op1, op2])
        self.output.extend(struct.pack('<I', offset & 0xFFFFFFFF))

    def _op_je(self, args):
        self._cond_jmp(0x0F, 0x84, args[0])

    def _op_jne(self, args):
        self._cond_jmp(0x0F, 0x85, args[0])

    def _op_jl(self, args):
        self._cond_jmp(0x0F, 0x8C, args[0])

    def _op_jg(self, args):
        self._cond_jmp(0x0F, 0x8F, args[0])

    def _op_call(self, args):
        offset = self.labels.get(args[0], 0) - (self.current_pos + 5)
        self.output.extend([0xE8])
        self.output.extend(struct.pack('<I', offset & 0xFFFFFFFF))

    def _op_ret(self, args):
        self.output.append(0xC3)

    def _op_push(self, args):
        self.output.append(0x50 + self.registers.get(args[0].upper(), 0))

    def _op_pop(self, args):
        self.output.append(0x58 + self.registers.get(args[0].upper(), 0))

    def _op_sys(self, args):
        self.output.extend([0x0F, 0x05])

    def _op_hlt(self, args):
        self.output.append(0xF4)

    def _op_nop(self, args):
        self.output.append(0x90)

    def _op_inc(self, args):
        self.output.extend([0x48, 0xFF, 0xC0 + self.registers.get(args[0].upper(), 0)])

    def _op_dec(self, args):
        self.output.extend([0x48, 0xFF, 0xC8 + self.registers.get(args[0].upper(), 0)])

    def _op_neg(self, args):
        self.output.extend([0x48, 0xF7, 0xD8 + self.registers.get(args[0].upper(), 0)])


class FluxExecutor:
    @staticmethod
    def run(machine_code: bytes) -> int:
        if SandboxGuard.is_remote():
            raise PermissionError("remote execution blocked")
        if sys.platform == "win32":
            MEM_COMMIT = 0x00001000
            MEM_RESERVE = 0x00002000
            PAGE_EXECUTE_READWRITE = 0x40
            size = len(machine_code)
            ptr = ctypes.windll.kernel32.VirtualAlloc(None, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
            if not ptr:
                raise OSError("VirtualAlloc failed")
            ctypes.memmove(ptr, machine_code, size)
            func_ptr = ctypes.cast(ptr, ctypes.CFUNCTYPE(ctypes.c_uint64))
            try:
                return func_ptr()
            finally:
                ctypes.windll.kernel32.VirtualFree(ptr, 0, 0x8000)
        else:
            import mmap
            exec_mem = mmap.mmap(-1, len(machine_code), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
            try:
                exec_mem.write(machine_code)
                exec_mem.flush()
                func_ptr = ctypes.cast(exec_mem, ctypes.CFUNCTYPE(ctypes.c_uint64))
                return func_ptr()
            finally:
                exec_mem.close()
