import os
os.environ["OHM_TEST_MODE"] = "1"
os.environ["OHM_RESISTANCE"] = "0.5"

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
MAIN = HERE / "ohm_synapse.py"

import importlib.util
spec = importlib.util.spec_from_file_location("ohm_mod", str(MAIN))
ohm = importlib.util.module_from_spec(spec)
sys.modules["ohm_mod"] = ohm
spec.loader.exec_module(ohm)

from ohm.llm import (
    LLMProvider, OllamaProvider, OpenAICompatProvider,
    AnthropicProvider, GoogleProvider, MockProvider,
    PROVIDER_REGISTRY, make_provider, _detect_provider,
    OllamaAdapter,
)


class TestEndpointNormalization(unittest.TestCase):
    def test_ollama_strips_api_generate(self):
        p = OllamaProvider({"endpoint": "http://localhost:11434/api/generate"})
        self.assertEqual(p.endpoint, "http://localhost:11434")

    def test_openai_strips_v1_chat_completions(self):
        p = OpenAICompatProvider({"endpoint": "https://api.openai.com/v1/chat/completions"})
        self.assertEqual(p.endpoint, "https://api.openai.com")

    def test_endpoint_trailing_slash_removed(self):
        p = OllamaProvider({"endpoint": "http://localhost:11434/"})
        self.assertEqual(p.endpoint, "http://localhost:11434")


class TestProviderRegistry(unittest.TestCase):
    def test_all_expected_names_present(self):
        for name in ("ollama", "openai", "openai_compat", "anthropic",
                     "claude", "google", "gemini", "mock",
                     "lmstudio", "vllm", "llamacpp"):
            self.assertIn(name, PROVIDER_REGISTRY)


class TestDetection(unittest.TestCase):
    def test_explicit_provider_wins(self):
        self.assertEqual(_detect_provider({"provider": "mock"}), "mock")
        self.assertEqual(_detect_provider({"provider": "anthropic"}), "anthropic")

    def test_detect_ollama_default(self):
        self.assertEqual(_detect_provider({"endpoint": "http://localhost:11434"}), "ollama")

    def test_detect_openai_from_endpoint(self):
        self.assertEqual(_detect_provider({"endpoint": "https://api.openai.com/v1"}), "openai_compat")

    def test_detect_anthropic_from_endpoint(self):
        self.assertEqual(_detect_provider({"endpoint": "https://api.anthropic.com"}), "anthropic")

    def test_detect_google_from_endpoint(self):
        self.assertEqual(_detect_provider({"endpoint": "https://generativelanguage.googleapis.com"}), "google")


class TestFactory(unittest.TestCase):
    def test_disabled_returns_none(self):
        self.assertIsNone(make_provider({"enabled": False}))

    def test_empty_returns_none(self):
        self.assertIsNone(make_provider({}))

    def test_ollama_factory(self):
        p = make_provider({"enabled": True, "provider": "ollama",
                           "endpoint": "http://localhost:11434"})
        self.assertIsInstance(p, OllamaProvider)

    def test_mock_factory(self):
        p = make_provider({"enabled": True, "provider": "mock"})
        self.assertIsInstance(p, MockProvider)


class TestCapabilities(unittest.TestCase):
    def test_mock_capabilities(self):
        p = MockProvider({"enabled": True, "provider": "mock",
                          "endpoint": "mock://", "model_name": "test"})
        caps = p.capabilities()
        self.assertEqual(caps["name"], "mock")
        self.assertEqual(caps["model"], "test")
        self.assertFalse(caps["supports_vision"])
        self.assertFalse(caps["supports_embeddings"])
        self.assertTrue(caps["available"])

    def test_openai_supports_vision_and_embeddings(self):
        p = OpenAICompatProvider({"endpoint": "http://x"})
        self.assertTrue(p.supports_vision)
        self.assertTrue(p.supports_embeddings)

    def test_anthropic_supports_vision(self):
        p = AnthropicProvider({"endpoint": "http://x"})
        self.assertTrue(p.supports_vision)
        self.assertFalse(p.supports_embeddings)

    def test_google_supports_both(self):
        p = GoogleProvider({"endpoint": "http://x"})
        self.assertTrue(p.supports_vision)
        self.assertTrue(p.supports_embeddings)


class TestMockBehavior(unittest.TestCase):
    def test_default_response(self):
        p = MockProvider({"enabled": True, "provider": "mock",
                          "default": "unknown"})
        text, _ = p.generate("hello")
        self.assertEqual(text, "unknown")

    def test_keyword_response(self):
        p = MockProvider({"enabled": True, "provider": "mock",
                          "responses": {"cat": "feline"}})
        text, _ = p.generate("what is a cat?")
        self.assertEqual(text, "feline")

    def test_is_available(self):
        p = MockProvider({"enabled": True, "provider": "mock"})
        self.assertTrue(p.is_available())


class TestBackwardCompat(unittest.TestCase):
    def test_adapter_with_disabled_config(self):
        cfg = ohm.OHMConfig()
        cfg.llm_cfg = dict(cfg.llm_cfg)
        cfg.llm_cfg["enabled"] = False
        a = OllamaAdapter(cfg)
        self.assertIsNone(a.provider)

    def test_adapter_with_mock(self):
        cfg = ohm.OHMConfig()
        cfg.llm_cfg = dict(cfg.llm_cfg)
        cfg.llm_cfg["enabled"] = True
        cfg.llm_cfg["provider"] = "mock"
        cfg.llm_cfg["endpoint"] = "mock://"
        cfg.llm_cfg["model_name"] = "test"
        cfg.llm_cfg["responses"] = {"hello": "hi there"}
        a = OllamaAdapter(cfg)
        text, _ = a.generate("hello world")
        self.assertEqual(text, "hi there")

    def test_adapter_capabilities(self):
        cfg = ohm.OHMConfig()
        cfg.llm_cfg = dict(cfg.llm_cfg)
        cfg.llm_cfg["enabled"] = True
        cfg.llm_cfg["provider"] = "mock"
        cfg.llm_cfg["endpoint"] = "mock://"
        cfg.llm_cfg["model_name"] = "test"
        a = OllamaAdapter(cfg)
        caps = a.capabilities()
        self.assertEqual(caps["name"], "mock")


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.brain = ohm.OHMSynapse()
        self.brain.llm = None

    def tearDown(self):
        self.brain.shutdown()

    def test_llm_command_disabled(self):
        r = self.brain.think("/llm")
        self.assertEqual(r.status, "LLM")
        self.assertIn("disabled", r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)