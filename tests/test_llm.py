import types

import httpx
import openai
import pytest

from magewise import llm

KEYS = ("NVIDIA_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "LLM_PROVIDERS", "LLM_MODEL", "LLM_BASE_URL",
        "LLM_API_KEY", "NVIDIA_MODEL", "GROQ_MODEL", "TOGETHER_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def fake_openai(monkeypatch, failing: set[str]):
    """OpenAI client stand-in: providers whose base_url contains a name in `failing` raise a 500."""
    calls = []

    class Client:
        def __init__(self, base_url, **_):
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, model, **_):
            calls.append(model)
            if any(n in self.base_url for n in failing):
                req = httpx.Request("POST", self.base_url)
                raise openai.InternalServerError("boom", response=httpx.Response(500, request=req), body=None)
            msg = types.SimpleNamespace(content=f"<think>x</think>answer from {model}")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm, "OpenAI", Client)
    return calls


def test_uses_only_providers_with_keys_in_preset_order(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    assert [p[0] for p in llm.providers()] == ["groq", "nvidia"]
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert [(p[0], p[3]) for p in llm.providers()] == [
        ("groq", "openai/gpt-oss-120b"), ("gemini", "gemini-3-flash-preview"), ("nvidia", "nvidia/nemotron-3-super-120b-a12b")]


def test_llm_providers_sets_order_and_models_can_be_overridden(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    monkeypatch.setenv("LLM_PROVIDERS", "groq,nvidia")
    monkeypatch.setenv("GROQ_MODEL", "llama-x")
    monkeypatch.setenv("LLM_MODEL", "old-nvidia-model")  # pre-multi-provider setting, still honored
    assert [(p[0], p[3]) for p in llm.providers()] == [("groq", "llama-x"), ("nvidia", "old-nvidia-model")]


def test_unknown_provider_is_an_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "groq,nope")
    with pytest.raises(ValueError, match="nope"):
        llm.providers()


def test_falls_back_to_next_provider_and_reports_which_answered(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("NVIDIA_API_KEY", "n")
    monkeypatch.setenv("LLM_PROVIDERS", "groq,nvidia")
    calls = fake_openai(monkeypatch, failing={"groq"})
    text, model = llm.llm("hi")
    assert calls == ["openai/gpt-oss-120b", "nvidia/nemotron-3-super-120b-a12b"]
    assert text == "answer from nvidia/nemotron-3-super-120b-a12b"  # <think> stripped
    assert model == "nvidia/nvidia/nemotron-3-super-120b-a12b"


def test_all_providers_failing_raises_with_every_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    fake_openai(monkeypatch, failing={"groq"})
    with pytest.raises(RuntimeError, match="groq: InternalServerError"):
        llm.llm("hi")
