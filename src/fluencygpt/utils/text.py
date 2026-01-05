from __future__ import annotations

import re


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace without changing meaning."""

    text = text.replace("\u00A0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text
