from __future__ import annotations

import json
import math
from typing import Any


def serialize_context(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def estimate_text_tokens(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(len(normalized.split()), math.ceil(len(normalized) / 4))


def estimate_tokens(value: Any) -> int:
    return estimate_text_tokens(serialize_context(value))


__all__ = ["estimate_text_tokens", "estimate_tokens", "serialize_context"]
