from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _loads_lenient(text: str) -> dict:
    """json.loads, but tolerate trailing commas (which some models emit)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", text))


def create_json(client: Any, model: str, messages: list, **kwargs):
    """Call chat.completions forcing JSON output when the endpoint supports it.

    Some NIM models reject ``response_format`` with a 400; only then do we fall
    back to a plain call. Other errors (timeouts, network, rate limits) are
    re-raised — retrying them here would silently double latency/cost.
    """
    try:
        return client.chat.completions.create(
            model=model, messages=messages,
            response_format={"type": "json_object"}, **kwargs)
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        if status == 400 or "response_format" in str(exc).lower():
            return client.chat.completions.create(
                model=model, messages=messages, **kwargs)
        raise


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
        return _loads_lenient(text)
    except json.JSONDecodeError:
        match = _JSON_OBJ.search(text)
        if match:
            return _loads_lenient(match.group(0))
        raise
