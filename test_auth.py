import os
import io
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent
import sys
sys.path.insert(0, str(HERE))

from ohm_auth import (
    AuthManager,
    generate_recovery_phrase,
    generate_session_token,
    auth_disabled_by_env,
    _hash_password,
    _verify_password,
    WORDLIST,
    RECOVERY_WORD_COUNT,
)


def make_auth(tmpdir):
    return AuthManager(Path(tmpdir))


class TestPasswordHashing(unittest.TestCase):
    def test_hash_verify_roundtrip(self):
        h = _hash_password("correct horse battery staple")
        self.assertTrue(_verify_password("correct horse battery staple", h))

    def test_wrong_password_fails(self):
        h = _hash_password("secret")
        self.assertFalse(_verify_password("other", h))

    def test_hash_is_not_plaintext(self):
        h = _hash_password("secret")
        self.assertNotIn("secret", h)


class TestRecoveryPhrase(unittest.TestCase):
    def test_generates_six_words(self):
        p = generate_recovery_phrase()
        words = p.split()
        self.assertEqual(len(words), RECOVERY_WORD_COUNT)
        for w in words:
            self.assertIn(w, WORDLIST)

    def test_phrases_differ(self):
        a = generate_recovery_phrase()
        b = generate_recovery_phrase()
        self.assertNotEqual(a, b)


class TestSessionToken(unittest.TestCase):
    def test_token_is_urlsafe_base64(self):
        t = generate_session_token()
        self.assertGreater(len(t), 30)
        self.assertNotIn("+", t)
        self.assertNotIn("/", t)

    def test_tokens_differ(self):
        a = generate_session_token()
        b = generate_session_token()
        self.assertNotEqual(a, b)


class TestAuthManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="ohm_auth_test_"))
        self.auth = make_auth(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_not_configured_initially(self):
        self.assertFalse(self.auth.configured)

    def test_configure_happy_path(self):
        phrase = self.auth.configure("mypassword", [
            ("Q1?", "a1"),
            ("Q2?", "a2"),
            ("Q3?", "a3"),
        ])
        self.assertTrue(self.auth.configured)
        self.assertGreater(len(phrase.split()), 0)

    def test_configure_rejects_short_password(self):
        with self.assertRaises(ValueError):
            self.auth.configure("abc", [("q", "a")] * 3)

    def test_configure_rejects_wrong_question_count(self):
        with self.assertRaises(ValueError):
            self.auth.configure("longpassword", [("q", "a")])
        with self.assertRaises(ValueError):
            self.auth.configure("longpassword", [("q", "a")] * 4)

    def test_configure_rejects_empty_answer(self):
        with self.assertRaises(ValueError):
            self.auth.configure("longpassword", [("q", "a"), ("q", ""), ("q", "c")])

    def test_verify_correct_password(self):
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        self.assertTrue(self.auth.verify_password("hunter2hunter2"))
        self.assertFalse(self.auth.verify_password("wrong"))

    def test_verify_phrase(self):
        phrase = self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        self.assertTrue(self.auth.verify_recovery_phrase(phrase))
        self.assertTrue(self.auth.verify_recovery_phrase(phrase.upper()))
        self.assertTrue(self.auth.verify_recovery_phrase("  " + phrase + "  "))
        self.assertFalse(self.auth.verify_recovery_phrase("wrong words here"))

    def test_verify_answers(self):
        self.auth.configure("hunter2hunter2", [
            ("first pet?", "rex"),
            ("mother name?", "Mary"),
            ("birth city?", "SP"),
        ])
        self.assertTrue(self.auth.verify_answers(["rex", "mary", "sp"]))
        self.assertTrue(self.auth.verify_answers(["REX", "  Mary  ", "sp"]))
        self.assertFalse(self.auth.verify_answers(["rex", "mary", "wrong"]))

    def test_get_questions_preserves_order_and_text(self):
        self.auth.configure("hunter2hunter2", [
            ("first pet?", "rex"),
            ("mother name?", "mary"),
            ("birth city?", "sp"),
        ])
        self.assertEqual(self.auth.get_questions(), ["first pet?", "mother name?", "birth city?"])

    def test_session_lifecycle(self):
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        token = self.auth.create_session()
        self.assertTrue(self.auth.validate_session(token))
        self.assertTrue(self.auth.revoke_session(token))
        self.assertFalse(self.auth.validate_session(token))

    def test_session_revoked_on_password_reset(self):
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        token = self.auth.create_session()
        self.auth.reset_password("newlongpassword")
        self.assertFalse(self.auth.validate_session(token))

    def test_reset_password_requires_config(self):
        with self.assertRaises(ValueError):
            self.auth.reset_password("longpassword")

    def test_reset_password_min_length(self):
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        with self.assertRaises(ValueError):
            self.auth.reset_password("short")

    def test_status(self):
        st = self.auth.status()
        self.assertFalse(st["configured"])
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        st = self.auth.status()
        self.assertTrue(st["configured"])
        self.assertEqual(st["questions_count"], 3)

    def test_persistence(self):
        self.auth.configure("hunter2hunter2", [("q", "a")] * 3)
        auth2 = make_auth(self.tmpdir)
        self.assertTrue(auth2.configured)
        self.assertTrue(auth2.verify_password("hunter2hunter2"))


class TestAuthDisabledEnv(unittest.TestCase):
    def setUp(self):
        self.old_test = os.environ.get("OHM_TEST_MODE")
        self.old_dis = os.environ.get("OHM_AUTH_DISABLED")

    def tearDown(self):
        for k, v in (("OHM_TEST_MODE", self.old_test), ("OHM_AUTH_DISABLED", self.old_dis)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_disabled_by_test_mode(self):
        os.environ["OHM_TEST_MODE"] = "1"
        os.environ.pop("OHM_AUTH_DISABLED", None)
        self.assertTrue(auth_disabled_by_env())

    def test_disabled_by_explicit_flag(self):
        os.environ.pop("OHM_TEST_MODE", None)
        os.environ["OHM_AUTH_DISABLED"] = "1"
        self.assertTrue(auth_disabled_by_env())

    def test_enabled_by_default(self):
        os.environ.pop("OHM_TEST_MODE", None)
        os.environ.pop("OHM_AUTH_DISABLED", None)
        self.assertFalse(auth_disabled_by_env())


if __name__ == "__main__":
    unittest.main(verbosity=2)