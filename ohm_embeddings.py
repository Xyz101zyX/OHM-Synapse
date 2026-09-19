# _OFFLINE_LOAD
import os
import json
import base64
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore[assignment]

HAS_ST: "Optional[bool]" = None
SentenceTransformer = None


def _ensure_st() -> bool:
    global HAS_ST, SentenceTransformer
    if HAS_ST is None:
        try:
            from sentence_transformers import SentenceTransformer as _ST
            SentenceTransformer = _ST
            HAS_ST = True
        except ImportError:
            HAS_ST = False
    return HAS_ST


DEFAULT_MODEL = "all-MiniLM-L6-v2"
DIM_FALLBACK = 384


_MODEL_CACHE: Dict[str, Any] = {}


def _get_cached_model(name: str):
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    if not _ensure_st():
        _MODEL_CACHE[name] = None
        return None
    try:
        m = SentenceTransformer(name, device="cpu", local_files_only=True)
    except Exception:
        # Not cached — try online once
        try:
            m = SentenceTransformer(name, device="cpu")
        except Exception:
            m = None
    _MODEL_CACHE[name] = m
    return m


def _model_dim(model) -> int:
    if model is None:
        return DIM_FALLBACK
    try:
        return model.get_sentence_embedding_dimension()
    except AttributeError:
        return model.get_embedding_dimension()
    except Exception:
        return DIM_FALLBACK


class EmbeddingManager:
    def __init__(self, config=None, enabled: bool = True):
        self.config = config or {}
        self.model_name = self.config.get("model", DEFAULT_MODEL)
        self.model = None
        self.dim = DIM_FALLBACK
        self.cache: Dict[str, Any] = {}
        self.available = False

        if not enabled:
            return
        if not HAS_NUMPY:
            return

        # Defer ALL imports and model loading.
        self.available = True
    
    def _ensure_model(self) -> bool:
        if self.model is not None:
            return True
        if not self.available:
            return False
        if not _ensure_st():
            self.available = False
            return False
        try:
            self.model = _get_cached_model(self.model_name)
            if self.model is None:
                self.available = False
                return False
            self.dim = _model_dim(self.model)
            return True
        except Exception:
            self.model = None
            self.available = False
            return False

    def _load_model(self):
        self._ensure_model()

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not self._ensure_model():
            return None
        key = text[:512]
        if key in self.cache:
            return self.cache[key]
        try:
            vec = self.model.encode(key, normalize_embeddings=True)  # type: ignore[union-attr]
            result = vec.tolist()
            if len(self.cache) < 4096:
                self.cache[key] = result
            return result
        except Exception:
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        if not self.available:
            return [None] * len(texts)
        try:
            cleaned = [(t or "")[:512] for t in texts]
            vecs = self.model.encode(cleaned, normalize_embeddings=True, batch_size=32)  # type: ignore[union-attr]
            return [v.tolist() for v in vecs]
        except Exception:
            return [None] * len(texts)

    def cosine(self, a: Optional[List[float]], b: Optional[List[float]]) -> float:
        if not a or not b:
            return 0.0
        if not HAS_NUMPY:
            return 0.0
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        denom = (np.linalg.norm(va) * np.linalg.norm(vb))
        if denom < 1e-9:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def encode_storage(self, vec: Optional[List[float]]) -> str:
        if not vec:
            return ""
        try:
            arr = np.array(vec, dtype=np.float32)
            raw = arr.tobytes()
            return base64.b64encode(raw).decode("ascii")
        except Exception:
            return ""

    def decode_storage(self, blob: str) -> Optional[List[float]]:
        if not blob or not HAS_NUMPY:
            return None
        try:
            raw = base64.b64decode(blob)
            arr = np.frombuffer(raw, dtype=np.float32)
            return arr.tolist()
        except Exception:
            return None

    def status(self) -> dict:
        return {
            "available": self.available,
            "model": self.model_name,
            "dim": self.dim,
            "cache_size": len(self.cache),
        }