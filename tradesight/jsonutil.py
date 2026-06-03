from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def create_json(client: Any, model: str, messages: list, **kwargs):
    """Call chat.completions forcing JSON output when the endpoint supports it.

    Some NIM models reject ``response_format``; if the forced-JSON call fails,
    fall back to a plain call so the request still goes through.
    """
    try:
        return client.chat.completions.create(
            model=model, messages=messages,
            response_format={"type": "json_object"}, **kwargs)
    except Exception:  # noqa: BLE001 — model may not support response_format
        return client.chat.completions.create(
            model=model, messages=messages, **kwargs)


def parse_json_object(text: str) -> dict:
    """Parse a JSON object from a model response.

    Tolerates ```json code fences and surrounding prose by falling back to the
    first ``{...}`` span. Raises json.JSONDecodeError if no object is found.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJ.search(text)
        if match:
            return json.loads(match.group(0))
        raise
