from __future__ import annotations

import json
import re

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


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
