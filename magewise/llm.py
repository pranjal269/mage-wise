"""The only place a model is called.

Providers are OpenAI-compatible endpoints tried in order: LLM_PROVIDERS="groq,nvidia" uses Groq and
falls back to NVIDIA when Groq errors, times out or rate-limits. Without LLM_PROVIDERS, every
provider whose API key is set is used, in PRESETS order. Override a provider's model with
<NAME>_MODEL (e.g. GROQ_MODEL). LLM_BASE_URL + LLM_API_KEY + LLM_MODEL add any other endpoint ("custom").
"""
import os
import re
import sys

import openai
from openai import OpenAI

# name: (base URL, API key env var, default model)
PRESETS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "nvidia/nemotron-3-super-120b-a12b"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "openai/gpt-oss-120b"),
}


def providers() -> list[tuple[str, str, str, str]]:
    """(name, base_url, api_key, model) for each configured provider, in fallback order."""
    table = {
        name: (url, os.environ.get(key_var, ""), os.environ.get(f"{name.upper()}_MODEL") or default)
        for name, (url, key_var, default) in PRESETS.items()
    }
    # LLM_MODEL predates multi-provider support and always meant the NVIDIA model.
    if os.environ.get("LLM_MODEL") and not os.environ.get("NVIDIA_MODEL") and not os.environ.get("LLM_BASE_URL"):
        table["nvidia"] = (table["nvidia"][0], table["nvidia"][1], os.environ["LLM_MODEL"])
    if os.environ.get("LLM_BASE_URL"):
        table["custom"] = (os.environ["LLM_BASE_URL"], os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_MODEL", ""))

    wanted = [p.strip() for p in os.environ.get("LLM_PROVIDERS", "").split(",") if p.strip()]
    unknown = [p for p in wanted if p not in table]
    if unknown:
        raise ValueError(f"unknown LLM_PROVIDERS {unknown}; known: {sorted(table)}")
    chosen = [(n, *table[n]) for n in (wanted or table) if table[n][1]]
    if not chosen:
        raise RuntimeError("no model provider configured: set GROQ_API_KEY, NVIDIA_API_KEY or TOGETHER_API_KEY")
    return chosen


def llm(prompt: str) -> tuple[str, str]:
    """Answer `prompt` with the first provider that works. Returns (text, "provider/model")."""
    errors = []
    for name, url, key, model in providers():
        # Few retries per provider: with a fallback configured, moving on beats waiting on a slow endpoint.
        client = OpenAI(base_url=url, api_key=key, max_retries=2, timeout=150)
        try:
            out = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], max_tokens=8192
            )
        except openai.APIError as e:  # 5xx, timeout, rate limit, auth: try the next provider
            errors.append(f"{name}: {type(e).__name__}: {e}")
            print(f"magewise: {name} failed ({type(e).__name__}), trying next provider", file=sys.stderr)
            continue
        text = out.choices[0].message.content or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip(), f"{name}/{model}"
    raise RuntimeError("all model providers failed:\n" + "\n".join(errors))
