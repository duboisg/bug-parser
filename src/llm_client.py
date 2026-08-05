import json
import re
from openai import OpenAI

LLM_BASE_URL = "http://127.0.0.1:8080/v1"
LLM_MODEL = "gemma4:e2b"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key="local")
    return _client


def chat(messages: list[dict], temperature: float = 0.1) -> str:
    resp = _get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def extract_json(text: str) -> dict:
    """Parse JSON from LLM response; tolerates markdown fences and leading prose."""
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)

    # Find first { ... } block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
