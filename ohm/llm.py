import os
import time
import base64
import requests
from typing import Any, Dict, List, Optional, Tuple


class LLMProvider:
    name = "base"
    supports_vision = False
    supports_embeddings = False
    supports_streaming = False

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        ep = (self.config.get("endpoint") or "").rstrip("/")
        for suffix in ("/api/generate", "/api/chat", "/api/embeddings",
                       "/v1/chat/completions", "/v1/completions"):
            if ep.endswith(suffix):
                ep = ep[:-len(suffix)]
                break
        self.endpoint = ep.rstrip("/")
        self.model = self.config.get("model_name") or ""
        self.timeout = float(self.config.get("timeout", 30))
        self.api_key_env = self.config.get("api_key_env") or ""
        if self.api_key_env:
            self.api_key = os.environ.get(self.api_key_env, "")
        else:
            self.api_key = self.config.get("api_key", "") or ""

    def generate(self, prompt: str) -> Tuple[str, float]:
        raise NotImplementedError

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        if not self.supports_vision:
            return "DIAGNOSTIC: vision not supported", 0.0
        raise NotImplementedError

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "endpoint": self.endpoint,
            "supports_vision": self.supports_vision,
            "supports_embeddings": self.supports_embeddings,
            "supports_streaming": self.supports_streaming,
            "available": self.is_available(),
        }


class OllamaProvider(LLMProvider):
    name = "ollama"
    supports_embeddings = True

    def generate(self, prompt: str) -> Tuple[str, float]:
        start = time.time()
        try:
            url = f"{self.endpoint}/api/generate"
            r = requests.post(url, json={
                "model": self.model, "prompt": prompt, "stream": False,
            }, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            return data.get("response", "[empty]"), time.time() - start
        except requests.exceptions.ConnectionError:
            return "DIAGNOSTIC: ollama offline", 0.0
        except requests.exceptions.ReadTimeout:
            return "DIAGNOSTIC: timeout", 0.0
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        start = time.time()
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            url = f"{self.endpoint}/api/generate"
            r = requests.post(url, json={
                "model": self.model, "prompt": prompt,
                "images": [b64], "stream": False,
            }, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            return data.get("response", "[empty]"), time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def embed(self, texts: List[str]) -> List[List[float]]:
        out = []
        for t in texts:
            try:
                r = requests.post(f"{self.endpoint}/api/embeddings",
                                  json={"model": self.model, "prompt": t},
                                  timeout=self.timeout)
                out.append(r.json().get("embedding", []))
            except Exception:
                out.append([])
        return out

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.endpoint}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"
    supports_vision = True
    supports_embeddings = True

    def _chat_url(self) -> str:
        ep = self.endpoint
        if ep.endswith("/v1"):
            return f"{ep}/chat/completions"
        return f"{ep}/v1/chat/completions"

    def _embeddings_url(self) -> str:
        ep = self.endpoint
        if ep.endswith("/v1"):
            return f"{ep}/embeddings"
        return f"{ep}/v1/embeddings"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def generate(self, prompt: str) -> Tuple[str, float]:
        start = time.time()
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
            r = requests.post(self._chat_url(), headers=self._headers(),
                              json=payload, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            choices = data.get("choices", [])
            if not choices:
                return "DIAGNOSTIC: empty response", 0.0
            content = choices[0].get("message", {}).get("content", "")
            return content, time.time() - start
        except requests.exceptions.ConnectionError:
            return "DIAGNOSTIC: endpoint offline", 0.0
        except requests.exceptions.ReadTimeout:
            return "DIAGNOSTIC: timeout", 0.0
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        start = time.time()
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
            payload = {"model": self.model,
                       "messages": [{"role": "user", "content": content}],
                       "stream": False}
            r = requests.post(self._chat_url(), headers=self._headers(),
                              json=payload, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            choices = data.get("choices", [])
            if not choices:
                return "DIAGNOSTIC: empty response", 0.0
            content_out = choices[0].get("message", {}).get("content", "")
            return content_out, time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            payload = {"model": self.model, "input": texts}
            r = requests.post(self._embeddings_url(), headers=self._headers(),
                              json=payload, timeout=self.timeout)
            data = r.json()
            return [item.get("embedding", []) for item in data.get("data", [])]
        except Exception:
            return [[] for _ in texts]

    def is_available(self) -> bool:
        try:
            ep = self.endpoint
            url = f"{ep}/models" if ep.endswith("/v1") else f"{ep}/v1/models"
            r = requests.get(url, headers=self._headers(), timeout=3)
            return r.status_code == 200
        except Exception:
            return False


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    supports_vision = True

    def _messages_url(self) -> str:
        ep = self.endpoint or "https://api.anthropic.com"
        if ep.endswith("/v1"):
            return f"{ep}/messages"
        return f"{ep}/v1/messages"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def generate(self, prompt: str) -> Tuple[str, float]:
        start = time.time()
        try:
            payload = {
                "model": self.model,
                "max_tokens": int(self.config.get("max_tokens", 1024)),
                "messages": [{"role": "user", "content": prompt}],
            }
            r = requests.post(self._messages_url(), headers=self._headers(),
                              json=payload, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            blocks = data.get("content", [])
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return text, time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        start = time.time()
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content = [
                {"type": "text", "text": prompt},
                {"type": "image",
                 "source": {"type": "base64", "media_type": mime, "data": b64}},
            ]
            payload = {
                "model": self.model,
                "max_tokens": int(self.config.get("max_tokens", 1024)),
                "messages": [{"role": "user", "content": content}],
            }
            r = requests.post(self._messages_url(), headers=self._headers(),
                              json=payload, timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            blocks = data.get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text"), time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0


class GoogleProvider(LLMProvider):
    name = "google"
    supports_vision = True
    supports_embeddings = True

    def _url(self, method: str) -> str:
        base = self.endpoint or "https://generativelanguage.googleapis.com"
        return f"{base}/v1beta/models/{self.model}:{method}?key={self.api_key}"

    def generate(self, prompt: str) -> Tuple[str, float]:
        start = time.time()
        try:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(self._url("generateContent"), json=payload,
                              timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            candidates = data.get("candidates", [])
            if not candidates:
                return "DIAGNOSTIC: empty response", 0.0
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts), time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        start = time.time()
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            payload = {"contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]}]}
            r = requests.post(self._url("generateContent"), json=payload,
                              timeout=self.timeout)
            data = r.json()
            if "error" in data:
                return f"DIAGNOSTIC: {data['error']}", 0.0
            candidates = data.get("candidates", [])
            if not candidates:
                return "DIAGNOSTIC: empty response", 0.0
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts), time.time() - start
        except Exception as e:
            return f"DIAGNOSTIC: {e}", 0.0


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.responses = self.config.get("responses", {}) or {}
        self.default = self.config.get("default", "I do not have that information.")

    def generate(self, prompt: str) -> Tuple[str, float]:
        for k, v in self.responses.items():
            if k.lower() in prompt.lower():
                return v, 0.001
        return self.default, 0.001

    def is_available(self) -> bool:
        return True


PROVIDER_REGISTRY = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatProvider,
    "openai_compat": OpenAICompatProvider,
    "lmstudio": OpenAICompatProvider,
    "vllm": OpenAICompatProvider,
    "llamacpp": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "google": GoogleProvider,
    "gemini": GoogleProvider,
    "mock": MockProvider,
}


def _detect_provider(config: Dict[str, Any]) -> str:
    name = (config.get("provider") or "").lower()
    if name in PROVIDER_REGISTRY:
        return name
    endpoint = (config.get("endpoint") or "").lower()
    if "anthropic" in endpoint:
        return "anthropic"
    if "generativelanguage.googleapis" in endpoint or "gemini" in endpoint:
        return "google"
    if "/v1/" in endpoint or "openai" in endpoint:
        return "openai_compat"
    return "ollama"


def make_provider(config: Dict[str, Any]) -> Optional[LLMProvider]:
    if not config:
        return None
    if not config.get("enabled", False):
        return None
    key = _detect_provider(config)
    cls = PROVIDER_REGISTRY.get(key)
    if cls is None:
        return None
    return cls(config)


class OllamaAdapter:
    def __init__(self, config):
        self.provider = make_provider(config.llm_cfg)
        self.url = config.llm_cfg.get("endpoint", "http://localhost:11434/api/generate")
        self.model = config.llm_cfg.get("model_name", "llama3.2:1b")
        self.timeout = config.llm_cfg.get("timeout", 30)

    def generate(self, prompt: str) -> Tuple[str, float]:
        if self.provider is None:
            return "DIAGNOSTIC: llm disabled", 0.0
        return self.provider.generate(prompt)

    def generate_with_image(self, prompt: str, image_bytes: bytes,
                            mime: str = "image/png") -> Tuple[str, float]:
        if self.provider is None:
            return "DIAGNOSTIC: llm disabled", 0.0
        return self.provider.generate_with_image(prompt, image_bytes, mime)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self.provider is None:
            return [[] for _ in texts]
        return self.provider.embed(texts)

    def capabilities(self) -> Dict[str, Any]:
        if self.provider is None:
            return {"name": "disabled", "available": False}
        return self.provider.capabilities()