import os

from groq import Groq

MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")


def llm(prompt: str, system: str = "") -> str:
    """The only place a model is called. Swap provider here (Groq reads GROQ_API_KEY)."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    return Groq().chat.completions.create(model=MODEL, messages=messages).choices[0].message.content
