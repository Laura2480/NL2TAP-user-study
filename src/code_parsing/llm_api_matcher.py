"""
LLM-based API name matcher — semantic replacement for difflib fuzzy matching.

Single LLM call maps all invalid getter/setter names to their best catalog match.
Falls back silently (returns {}) on any failure so the caller can continue without suggestions.
"""
import json
import re
from typing import Dict, List, Optional

import requests


def match_api_names(
    invalids: List[str],
    allowed_pool: List[str],
    endpoint: str,
    model: str,
    timeout: int = 30,
) -> Dict[str, Optional[str]]:
    """
    Use an LLM to semantically match invalid API names to their best valid counterpart.

    Args:
        invalids: invalid accessor names (e.g. ["Weather.X.MinTemperatureCelsius"])
        allowed_pool: valid names from the catalog
        endpoint: OpenAI-compatible chat completions URL
        model: model identifier
        timeout: request timeout in seconds

    Returns:
        Mapping {invalid_name: best_match_or_None}. Empty dict on any failure.
    """
    if not invalids or not allowed_pool:
        return {}

    invalids_formatted = "\n".join(f"- {name}" for name in invalids)
    pool_formatted = "\n".join(f"- {name}" for name in sorted(allowed_pool))

    system_prompt = (
        "You are an API name matcher. Given a list of INVALID API accessor names "
        "and a list of VALID names from the catalog, find the best semantic match "
        "for each invalid name.\n\n"
        "INVALID names:\n"
        f"{invalids_formatted}\n\n"
        "VALID names (pick from these only):\n"
        f"{pool_formatted}\n\n"
        "Return a JSON object mapping each invalid name to its best match, "
        "or null if no reasonable match exists.\n"
        "Return ONLY the JSON object, no other text."
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": system_prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return {}

    return _parse_match_response(raw, invalids, allowed_pool)


def _parse_match_response(
    raw: str,
    invalids: List[str],
    allowed_pool: List[str],
) -> Dict[str, Optional[str]]:
    """Parse LLM response into a validated mapping."""
    data = _try_extract_json(raw)
    if not isinstance(data, dict):
        return {}

    pool_set = set(allowed_pool)
    result: Dict[str, Optional[str]] = {}
    for inv in invalids:
        match = data.get(inv)
        if match is None or match in pool_set:
            result[inv] = match
        else:
            # LLM returned a name not in the pool — discard
            result[inv] = None

    return result


def _try_extract_json(raw: str) -> Optional[dict]:
    """Extract a JSON object from LLM output (handles markdown code blocks, Qwen3 <think> tags)."""
    # Strip Qwen3 thinking tags before parsing
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    stripped = raw.strip()

    # 1. Direct parse
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Markdown code block
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. First { to last }
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        try:
            data = json.loads(raw[first:last + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    return None
