import os
import json
import time
import base64
import queue
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption,
        load_pem_private_key, load_pem_public_key,
    )
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


DEFAULT_SESSION_TTL = 604800


class OHMChat:
    def __init__(self, ohm_instance, mqtt_client, node_id: str):
        self.ohm = ohm_instance
        self.mqtt = mqtt_client
        self.node_id = node_id
        self.enabled = HAS_CRYPTO

        self.session_ttl = DEFAULT_SESSION_TTL
        try:
            chat_cfg = self.ohm.config.raw.get("chat", {}) or {}
            self.session_ttl = int(chat_cfg.get("session_ttl_seconds", DEFAULT_SESSION_TTL))
        except Exception:
            pass

        self._private_key = None
        self._public_key = None
        self.public_pem = ""

        if self.enabled:
            self._private_key = self._load_or_create_ecdh_key()
            if self._private_key is not None:
                self._public_key = self._private_key.public_key()
                self.public_pem = self._public_key.public_bytes(
                    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
                ).decode()

        self._session_keys: Dict[str, bytes] = {}
        self._session_meta: Dict[str, Dict[str, float]] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = {}
        self.contacts: Dict[str, Dict[str, Any]] = {}
        self.inbox: queue.Queue = queue.Queue()

        self._load_history()
        self._load_contacts()
        self._load_sessions()

        if self.mqtt and self.mqtt.client is not None and self.enabled:
            try:
                self.mqtt.client.subscribe(f"ohm/chat/handshake/{self.node_id}")
                self.mqtt.client.subscribe(f"ohm/chat/msg/{self.node_id}")
            except Exception:
                pass

    def _data_dir(self) -> Optional[Path]:
        try:
            pf = self.ohm.config.memory_cfg.get("persistence_file", "./mem.json")
            return Path(pf).parent
        except Exception:
            return None

    def _ecdh_path(self):
        d = self._data_dir()
        return (d / "chat_ecdh.pem") if d else None

    def _sessions_path(self):
        d = self._data_dir()
        return (d / "chat_sessions.json") if d else None

    def _history_path(self):
        d = self._data_dir()
        return (d / "chat_history.json") if d else None

    def _contacts_path(self):
        d = self._data_dir()
        return (d / "contacts.json") if d else None

    def _load_or_create_ecdh_key(self):
        path = self._ecdh_path()
        if path is not None and path.exists():
            try:
                return load_pem_private_key(path.read_bytes(), password=None)
            except Exception:
                pass
        key = ec.generate_private_key(ec.SECP384R1())
        if path is not None:
            try:
                pem = key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.PKCS8,
                    encryption_algorithm=NoEncryption(),
                )
                path.write_bytes(pem)
            except Exception:
                pass
        return key

    def _load_sessions(self):
        path = self._sessions_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        now = time.time()
        for peer_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            key_b64 = entry.get("key", "")
            expires = float(entry.get("expires", 0))
            created = float(entry.get("created", now))
            if not key_b64 or expires <= now:
                continue
            try:
                self._session_keys[peer_id] = base64.b64decode(key_b64)
                self._session_meta[peer_id] = {"created": created, "expires": expires}
            except Exception:
                continue

    def _save_sessions(self):
        path = self._sessions_path()
        if path is None:
            return
        now = time.time()
        out: Dict[str, Dict[str, Any]] = {}
        for peer_id, key in self._session_keys.items():
            meta = self._session_meta.get(peer_id) or {}
            created = float(meta.get("created", now))
            expires = float(meta.get("expires", now + self.session_ttl))
            if expires <= now:
                continue
            out[peer_id] = {
                "key": base64.b64encode(key).decode(),
                "created": created,
                "expires": expires,
            }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            pass

    def _prune_sessions(self):
        now = time.time()
        drop = []
        for peer_id, key in list(self._session_keys.items()):
            meta = self._session_meta.get(peer_id) or {}
            expires = float(meta.get("expires", 0))
            if expires and expires <= now:
                drop.append(peer_id)
        for peer_id in drop:
            self._session_keys.pop(peer_id, None)
            self._session_meta.pop(peer_id, None)
        if drop:
            self._save_sessions()

    def _load_history(self):
        path = self._history_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.history = {k: v for k, v in data.items() if isinstance(v, list)}
        except Exception:
            pass

    def _save_history(self):
        path = self._history_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_contacts(self):
        path = self._contacts_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.contacts = {k: v for k, v in data.items() if isinstance(v, dict)}
        except Exception:
            pass

    def _save_contacts(self):
        path = self._contacts_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.contacts, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _touch_contact(self, peer_id: str, direction: str, message: str):
        if not peer_id:
            return
        now = time.time()
        c = self.contacts.get(peer_id)
        if c is None:
            c = {
                "peer_id": peer_id,
                "alias": "",
                "first_seen": now,
                "last_seen": now,
                "message_count": 0,
                "last_message": "",
                "last_direction": "",
            }
            self.contacts[peer_id] = c
        c["last_seen"] = now
        c["message_count"] = int(c.get("message_count", 0)) + 1
        c["last_message"] = (message or "")[:80]
        c["last_direction"] = direction
        self._save_contacts()

    def _emit_audit_safe(self, event: str, meta: Dict[str, Any]):
        try:
            if hasattr(self.ohm, "_emit_audit"):
                self.ohm._emit_audit({"event": event, **meta})
        except Exception:
            pass

    def has_session(self, peer_id: str) -> bool:
        if peer_id not in self._session_keys:
            return False
        meta = self._session_meta.get(peer_id) or {}
        expires = float(meta.get("expires", 0))
        return expires > time.time()

    def session_remaining(self, peer_id: str) -> float:
        meta = self._session_meta.get(peer_id) or {}
        expires = float(meta.get("expires", 0))
        return max(0.0, expires - time.time())

    def send_handshake(self, peer_id: str) -> bool:
        if not self.enabled or self.mqtt is None or not self.mqtt.enabled:
            return False
        payload = {
            "from": self.node_id,
            "public_pem": self.public_pem,
            "timestamp": time.time(),
        }
        self.mqtt.publish(f"ohm/chat/handshake/{peer_id}", payload)
        self._touch_contact(peer_id, "handshake_out", "")
        return True

    def handle_handshake(self, payload: Dict[str, Any]) -> bool:
        if not self.enabled or self._private_key is None:
            return False
        peer_id = payload.get("from")
        peer_pem = payload.get("public_pem")
        if not peer_id or not peer_pem:
            return False
        try:
            peer_pub = load_pem_public_key(peer_pem.encode())
            shared = self._private_key.exchange(ec.ECDH(), peer_pub)
            session_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"ohm-chat-v1",
            ).derive(shared)
            now = time.time()
            self._session_keys[peer_id] = session_key
            self._session_meta[peer_id] = {
                "created": now,
                "expires": now + self.session_ttl,
            }
            self._save_sessions()
            self._emit_audit_safe("chat_handshake", {"peer": peer_id, "ttl": self.session_ttl})
            self._touch_contact(peer_id, "handshake_in", "")
            if not payload.get("is_reply"):
                reply = {
                    "from": self.node_id,
                    "public_pem": self.public_pem,
                    "timestamp": time.time(),
                    "is_reply": True,
                }
                self.mqtt.publish(f"ohm/chat/handshake/{peer_id}", reply)
            return True
        except Exception as e:
            self._emit_audit_safe("chat_handshake_failed", {"peer": peer_id, "error": str(e)})
            return False

    def _encrypt(self, peer_id: str, plaintext: str) -> Optional[str]:
        key = self._session_keys.get(peer_id)
        if not key:
            return None
        nonce = os.urandom(12)
        aes = AESGCM(key)
        ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def _decrypt(self, peer_id: str, encrypted: str) -> Optional[str]:
        key = self._session_keys.get(peer_id)
        if not key:
            return None
        try:
            blob = base64.b64decode(encrypted)
            nonce, ciphertext = blob[:12], blob[12:]
            aes = AESGCM(key)
            return aes.decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception:
            return None

    def send(self, peer_id: str, message: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "CHAT_DISABLED", "reason": "cryptography not available"}
        if self.mqtt is None or not self.mqtt.enabled:
            return {"status": "MQTT_OFFLINE", "peer": peer_id}
        self._prune_sessions()
        if not self.has_session(peer_id):
            self.send_handshake(peer_id)
            return {"status": "HANDSHAKE_SENT", "peer": peer_id}
        encrypted = self._encrypt(peer_id, message)
        if not encrypted:
            return {"status": "ENCRYPT_FAILED", "peer": peer_id}
        payload = {
            "from": self.node_id,
            "to": peer_id,
            "data": encrypted,
            "timestamp": time.time(),
        }
        self.mqtt.publish(f"ohm/chat/msg/{peer_id}", payload)
        self.history.setdefault(peer_id, []).append({
            "role": "user", "content": message, "ts": time.time(),
        })
        self._save_history()
        self._touch_contact(peer_id, "out", message)
        self._emit_audit_safe("chat_sent", {"peer": peer_id, "length": len(message)})
        return {"status": "SENT", "peer": peer_id, "encrypted": True}

    def receive(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        peer_id = payload.get("from")
        encrypted = payload.get("data")
        if not peer_id or not encrypted:
            return None
        plaintext = self._decrypt(peer_id, encrypted)
        if plaintext is None:
            return {"status": "DECRYPT_FAILED", "peer": peer_id}
        self.history.setdefault(peer_id, []).append({
            "role": "peer", "content": plaintext, "ts": time.time(),
        })
        self._save_history()
        self._touch_contact(peer_id, "in", plaintext)
        self._emit_audit_safe("chat_received", {"peer": peer_id, "length": len(plaintext)})
        return {"status": "RECEIVED", "peer": peer_id, "message": plaintext}

    def get_history(self, peer_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.history.get(peer_id, [])[-limit:]

    def list_peers(self) -> List[str]:
        return list(self._session_keys.keys())

    def list_contacts(self) -> List[Dict[str, Any]]:
        items = list(self.contacts.values())
        items.sort(key=lambda c: c.get("last_seen", 0), reverse=True)
        return items

    def set_alias(self, peer_id: str, alias: str) -> bool:
        if not peer_id:
            return False
        c = self.contacts.get(peer_id)
        if c is None:
            self._touch_contact(peer_id, "alias_only", "")
            c = self.contacts.get(peer_id)
        if c is None:
            return False
        c["alias"] = (alias or "").strip()[:40]
        self._save_contacts()
        return True

    def remove_contact(self, peer_id: str) -> bool:
        if not peer_id:
            return False
        removed = False
        if peer_id in self.contacts:
            del self.contacts[peer_id]
            removed = True
            self._save_contacts()
        if peer_id in self._session_keys:
            del self._session_keys[peer_id]
            self._session_meta.pop(peer_id, None)
            self._save_sessions()
            removed = True
        return removed

    def clear_session(self, peer_id: str) -> bool:
        if peer_id in self._session_keys:
            del self._session_keys[peer_id]
            self._session_meta.pop(peer_id, None)
            self._save_sessions()
            return True
        return False

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "node_id": self.node_id,
            "public_key": (self.public_pem[:64] + "...") if self.public_pem else "",
            "active_sessions": len(self._session_keys),
            "peers": list(self._session_keys.keys()),
            "contacts": len(self.contacts),
            "session_ttl_seconds": self.session_ttl,
            "total_messages": sum(len(v) for v in self.history.values()),
        }