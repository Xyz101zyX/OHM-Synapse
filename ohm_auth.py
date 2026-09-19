import os
import json
import time
import hmac
import hashlib
import secrets
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


BCRYPT_ROUNDS = 12
SESSION_TTL_SECONDS = 7 * 24 * 3600
RECOVERY_WORD_COUNT = 6

WORDLIST = [
    "anchor", "arrow", "atlas", "aurora", "basalt", "bishop", "bison", "blaze",
    "boulder", "breeze", "bridge", "bronze", "cactus", "camel", "canyon", "cedar",
    "cherry", "cipher", "cobalt", "copper", "coral", "cosmos", "cotton", "crater",
    "crystal", "cypress", "dahlia", "dawn", "delta", "dolphin", "dragon", "dune",
    "eagle", "ember", "emerald", "falcon", "fathom", "fern", "flint", "forest",
    "fossil", "fox", "galaxy", "garden", "glacier", "glow", "granite", "grotto",
    "harbor", "hazel", "heather", "helix", "horizon", "hunter", "indigo", "ivory",
    "jade", "jasmine", "jungle", "juniper", "kelp", "kestrel", "kite", "lagoon",
    "lantern", "larch", "laser", "lava", "lemon", "lichen", "lilac", "lotus",
    "lunar", "lynx", "magnet", "mango", "maple", "marble", "meadow", "mesa",
    "meteor", "mint", "mirror", "mist", "monsoon", "moss", "mural", "nebula",
    "nectar", "nickel", "nimbus", "north", "nova", "oak", "oasis", "ocean",
    "olive", "onyx", "opaque", "orchid", "otter", "oxide", "palm", "panther",
    "pebble", "penguin", "pepper", "petal", "phoenix", "pilot", "pioneer", "plasma",
    "plateau", "pollen", "pond", "poppy", "prairie", "prism", "puma", "quartz",
    "quill", "rain", "raven", "reef", "ridge", "river", "robin", "rocket",
    "rose", "rune", "saffron", "sage", "salmon", "sapphire", "savanna", "scarlet",
    "shadow", "signal", "silver", "siren", "sky", "snow", "solar", "sonnet",
    "sparrow", "spruce", "star", "stone", "storm", "summit", "sunrise", "surge",
    "swan", "tangle", "thistle", "thunder", "tiger", "timber", "topaz", "torch",
    "trail", "tulip", "tundra", "turquoise", "valley", "vapor", "velvet", "vertex",
    "violet", "volcano", "voyage", "walnut", "wave", "willow", "wind", "winter",
    "wolf", "wren", "xenon", "yarrow", "yew", "zenith", "zephyr", "zinc",
]


def _now() -> float:
    return time.time()


def _hash_password(password: str) -> str:
    if not HAS_BCRYPT:
        return hashlib.sha256(("OHM_NO_BCRYPT:" + password).encode("utf-8")).hexdigest()
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _verify_password(password: str, hashed: str) -> bool:
    if not HAS_BCRYPT:
        expected = hashlib.sha256(("OHM_NO_BCRYPT:" + password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, hashed)
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except Exception:
        return False


def _hash_answer(answer: str) -> str:
    normalized = (answer or "").strip().lower()
    return _hash_password(normalized)


def _verify_answer(answer: str, hashed: str) -> bool:
    return _verify_password((answer or "").strip().lower(), hashed)


def generate_recovery_phrase() -> str:
    words = [secrets.choice(WORDLIST) for _ in range(RECOVERY_WORD_COUNT)]
    return " ".join(words)


def _normalize_phrase(phrase: str) -> str:
    return " ".join((phrase or "").strip().lower().split())


def _hash_phrase(phrase: str) -> str:
    return _hash_password(_normalize_phrase(phrase))


def _verify_phrase(phrase: str, hashed: str) -> bool:
    return _verify_password(_normalize_phrase(phrase), hashed)


def generate_session_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthManager:
    def __init__(self, peer_dir: Path):
        self.peer_dir = Path(peer_dir)
        self.auth_file = self.peer_dir / "auth.json"
        self.sessions_file = self.peer_dir / "sessions.json"
        self._data: Dict[str, Any] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.auth_file.exists():
            try:
                self._data = json.loads(self.auth_file.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        if self.sessions_file.exists():
            try:
                self._sessions = json.loads(self.sessions_file.read_text(encoding="utf-8"))
            except Exception:
                self._sessions = {}
        self._prune_sessions()

    def _save(self):
        self.peer_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.auth_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self.auth_file)

    def _save_sessions(self):
        self.peer_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.sessions_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")
        os.replace(tmp, self.sessions_file)

    def _prune_sessions(self):
        now = _now()
        drop = [k for k, v in self._sessions.items() if v.get("expires", 0) <= now]
        for k in drop:
            del self._sessions[k]
        if drop:
            self._save_sessions()

    @property
    def configured(self) -> bool:
        return bool(self._data.get("password_hash"))

    def configure(self, password: str, questions: List[Tuple[str, str]]) -> str:
        if not password or len(password) < 6:
            raise ValueError("password must be at least 6 characters")
        if len(questions) != 3:
            raise ValueError("exactly 3 personal questions required")
        for q, a in questions:
            if not q or not q.strip():
                raise ValueError("question text cannot be empty")
            if not a or not a.strip():
                raise ValueError("answer cannot be empty")
        phrase = generate_recovery_phrase()
        self._data = {
            "version": 1,
            "created": _now(),
            "password_hash": _hash_password(password),
            "phrase_hash": _hash_phrase(phrase),
            "questions": [
                {"q": q.strip(), "a_hash": _hash_answer(a)}
                for q, a in questions
            ],
        }
        self._save()
        return phrase

    def verify_password(self, password: str) -> bool:
        if not self.configured:
            return True
        return _verify_password(password, self._data.get("password_hash", ""))

    def verify_recovery_phrase(self, phrase: str) -> bool:
        if not self.configured:
            return False
        return _verify_phrase(phrase, self._data.get("phrase_hash", ""))

    def verify_answers(self, answers: List[str]) -> bool:
        if not self.configured:
            return False
        questions = self._data.get("questions", [])
        if len(answers) != len(questions):
            return False
        for q, a in zip(questions, answers):
            if not _verify_answer(a, q.get("a_hash", "")):
                return False
        return True

    def get_questions(self) -> List[str]:
        return [q.get("q", "") for q in self._data.get("questions", [])]

    def reset_password(self, new_password: str) -> None:
        if not new_password or len(new_password) < 6:
            raise ValueError("password must be at least 6 characters")
        if not self.configured:
            raise ValueError("auth not configured")
        self._data["password_hash"] = _hash_password(new_password)
        self._data["updated"] = _now()
        self._save()
        self.revoke_all_sessions()

    def create_session(self, ttl: int = SESSION_TTL_SECONDS) -> str:
        token = generate_session_token()
        token_hash = _hash_token(token)
        now = _now()
        self._sessions[token_hash] = {
            "created": now,
            "expires": now + ttl,
            "last_used": now,
        }
        self._save_sessions()
        return token

    def validate_session(self, token: str) -> bool:
        if not token:
            return False
        self._prune_sessions()
        token_hash = _hash_token(token)
        entry = self._sessions.get(token_hash)
        if not entry:
            return False
        if entry.get("expires", 0) <= _now():
            self._sessions.pop(token_hash, None)
            self._save_sessions()
            return False
        entry["last_used"] = _now()
        self._save_sessions()
        return True

    def revoke_session(self, token: str) -> bool:
        token_hash = _hash_token(token)
        if token_hash in self._sessions:
            del self._sessions[token_hash]
            self._save_sessions()
            return True
        return False

    def revoke_all_sessions(self) -> int:
        n = len(self._sessions)
        self._sessions = {}
        self._save_sessions()
        return n

    def list_sessions(self) -> List[Dict[str, Any]]:
        self._prune_sessions()
        return [
            {"hash_prefix": k[:12], "created": v.get("created"), "expires": v.get("expires"),
             "last_used": v.get("last_used")}
            for k, v in self._sessions.items()
        ]

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "questions_count": len(self._data.get("questions", [])),
            "sessions": len(self._sessions),
            "created": self._data.get("created"),
        }


def auth_disabled_by_env() -> bool:
    if os.environ.get("OHM_AUTH_DISABLED") == "1":
        return True
    if os.environ.get("OHM_TEST_MODE") == "1":
        return True
    return False