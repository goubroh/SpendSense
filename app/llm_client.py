"""LangChain clients for Google Gemini, Groq, and OpenRouter, with offline fallback."""
import json
import os
import re


_PROVIDERS = {
    "google": ("GOOGLE_API_KEY", "Gemini", "gemini-2.5-flash"),
    "groq": ("GROQ_API_KEY", "Groq", "llama-3.3-70b-versatile"),
    "openrouter": ("OPENROUTER_API_KEY", "OpenRouter", "google/gemini-2.5-flash"),
}


def _selected_provider() -> str | None:
    provider = os.getenv("LLM_PROVIDER", "google").strip().lower() or "google"
    if provider == "auto":
        return next((name for name, (key, _, _) in _PROVIDERS.items() if os.getenv(key)), None)
    if provider not in _PROVIDERS:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Choose google, groq, openrouter, or auto.")
    return provider


def get_llm():
    provider = _selected_provider()
    if provider is None:
        return None
    key_name, _, default_model = _PROVIDERS[provider]
    api_key = os.getenv(key_name)
    if not api_key:
        return None
    model = os.getenv("LLM_MODEL", default_model)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=0.2)
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=api_key, temperature=0.2)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.2,
    )


def ask(llm, system: str, user: str) -> str | None:
    if llm is None:
        return None
    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        r = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        c = r.content
        return c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))
    except Exception as e:  # network / quota: degrade gracefully
        return None


def ask_json(llm, system: str, user: str) -> dict | None:
    text = ask(llm, system, user)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def status() -> str:
    provider = _selected_provider()
    if provider is None:
        return "LLM: offline mode (no supported provider key configured)."
    key_name, name, _ = _PROVIDERS[provider]
    if os.getenv(key_name):
        return f"LLM: {name}"
    return f"LLM: offline mode (set {key_name} for {name})."
