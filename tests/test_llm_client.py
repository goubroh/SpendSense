import sys
from types import ModuleType

import pytest

from app.llm_client import get_llm, status


@pytest.mark.parametrize(
    ("provider", "module_name", "class_name", "api_key_name", "model", "status_name"),
    [
        ("google", "langchain_google_genai", "ChatGoogleGenerativeAI", "GOOGLE_API_KEY", "gemini-2.5-flash", "Gemini"),
        ("groq", "langchain_groq", "ChatGroq", "GROQ_API_KEY", "llama-test", "Groq"),
        ("openrouter", "langchain_openai", "ChatOpenAI", "OPENROUTER_API_KEY", "google/gemini-test", "OpenRouter"),
    ],
)
def test_get_llm_uses_selected_provider(monkeypatch, provider, module_name, class_name, api_key_name, model, status_name):
    class FakeChat:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = ModuleType(module_name)
    setattr(module, class_name, FakeChat)
    monkeypatch.setitem(sys.modules, module_name, module)
    for key in ("GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(key, "test-key" if key == api_key_name else "")
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", model)

    llm = get_llm()

    assert isinstance(llm, FakeChat)
    assert llm.kwargs["model"] == model
    assert status() == f"LLM: {status_name}"
    if provider == "openrouter":
        assert llm.kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_get_llm_does_not_fall_back_when_selected_key_is_missing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    assert get_llm() is None
    assert "GOOGLE_API_KEY" in status()


def test_auto_provider_uses_first_configured_supported_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    assert status() == "LLM: Groq"


def test_get_llm_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unsupported-provider")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm()
