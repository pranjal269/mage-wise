import os
import re

from openai import OpenAI

# NVIDIA's API is OpenAI-compatible. Check the exact model id on build.nvidia.com.
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")


def llm(prompt: str, system: str = "") -> str:
    """The only place a model is called. Swap provider here."""
    # NVIDIA's hosted endpoint throws sporadic 500s and slow responses; retry instead of failing the request.
    client = OpenAI(base_url=BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], max_retries=5, timeout=180)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    out = client.chat.completions.create(model=MODEL, messages=messages, max_tokens=8192)
    text = out.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
