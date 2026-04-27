from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from fluencygpt.utils.text import normalize_whitespace


# Filler words commonly present in ASR transcripts.
_FILLERS = {"um", "uh", "er", "erm", "ah"}


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Try a few model IDs because provider catalogs can change over time.
_DEFAULT_OPENROUTER_MODELS = [
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]


def _is_word_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?", token))


def _strip_stutter_hyphens(text: str) -> str:
    """Collapse hyphen stutters like 'b-b-because' -> 'because'."""

    pattern = re.compile(r"\b([A-Za-z])(?:-\1)+-?([A-Za-z][A-Za-z']*)\b")
    prev = None
    cur = text
    while prev != cur:
        prev = cur
        cur = pattern.sub(r"\2", cur)
    return cur


def normalize_prolongations(text: str) -> str:
    """Normalize prolonged characters like 'wwwhat' / 'reallly' / 'ssssorry'.

        Rules (heuristic, deterministic):
        - Any vowel repeated 3+ times collapses to a single vowel ("pleeease" -> "please").
        - Any consonant repeated 3+ times collapses to a double consonant ("reallly" -> "really").
        - Any word-initial repeated letter collapses to a single letter ("wwwhat" -> "what").
        - Any doubled consonant that follows another consonant collapses to a single consonant
            ("thhhis" -> "this" after the first reduction step).

    Examples:
    - 'wwwhat' -> 'what'
    - 'thhhis' -> 'this'
    - 'pleeease' -> 'please'
    """

    vowels = {"a", "e", "i", "o", "u"}

    word_re = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

    def reduce_runs(word: str) -> str:
        # 1) Reduce 3+ repeated letters.
        def _reduce(m: re.Match[str]) -> str:
            ch = m.group(1)
            return ch if ch.lower() in vowels else (ch + ch)

        word = re.sub(r"([A-Za-z])\1{2,}", _reduce, word, flags=re.IGNORECASE)

        # 2) Remove any word-initial repeats (covers "wwhat" and "ssorry").
        word = re.sub(r"^([A-Za-z])\1+", r"\1", word, flags=re.IGNORECASE)

        # 3) Collapse doubled consonants that follow another consonant ("thhis" -> "this").
        def _collapse_doubled_consonant(m: re.Match[str]) -> str:
            prev = m.group(1)
            ch = m.group(2)
            if prev.lower() not in vowels and ch.lower() not in vowels:
                return prev + ch
            return prev + ch + ch

        word = re.sub(r"([A-Za-z])([A-Za-z])\2", _collapse_doubled_consonant, word)
        return word

    return word_re.sub(lambda m: reduce_runs(m.group(0)), text)


def _pre_normalize_for_llm(text: str) -> str:
    """Cheap, deterministic cleanup before the LLM call.

    This reduces token count and removes obvious stutter artefacts while keeping meaning.
    """

    cleaned = normalize_whitespace(text)
    cleaned = _strip_stutter_hyphens(cleaned)
    cleaned = normalize_prolongations(cleaned)
    return cleaned


def _openrouter_llm_rewrite(*, text: str, api_key: str, model: str) -> str:
    """Rewrite using OpenRouter's OpenAI-compatible Chat Completions API.

    Why OpenRouter:
    - It provides a single OpenAI-compatible endpoint for multiple models.
    - It keeps this project simple: a single HTTPS POST, no extra SDK dependencies.

    Stability:
    - Low temperature for deterministic-ish outputs
    - Short max_tokens to keep latency/cost down
    - Tight timeout so weak laptops don't hang
    """

    system_prompt = (
        "Rewrite the user's text into fluent English, removing stutters/fillers and repetitions, "
        "while preserving the original meaning. Output ONLY the rewritten text."
    )

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 128,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _OPENROUTER_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "FluencyGPT",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        content = (
            (((parsed.get("choices") or [{}])[0]).get("message") or {}).get("content")
            if isinstance(parsed, dict)
            else None
        )
        if not isinstance(content, str):
            raise ValueError("OpenRouter returned an unexpected response")
        return content.strip().strip('"').strip()
    except urllib.error.HTTPError as exc:
        # Keep the error generic; endpoints should fall back silently to rule-based rewrite.
        raise RuntimeError(f"OpenRouter HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenRouter request failed") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenRouter returned invalid JSON") from exc


def _join_tokens(tokens: list[str]) -> str:
    """Join tokens with simple punctuation spacing rules."""

    no_space_before = {".", ",", "!", "?", ";", ":", ")", "]", "}"}
    no_space_after = {"(", "[", "{"}

    out: list[str] = []
    for tok in tokens:
        if not out:
            out.append(tok)
            continue

        prev = out[-1]

        if tok in no_space_before:
            out[-1] = prev + tok
            continue

        if prev in no_space_after:
            out.append(tok)
            continue

        out.append(" " + tok)

    return "".join(out)


@dataclass(frozen=True)
class FluencyRewriter:
    # Deterministic, explainable rewriting (baseline + fallback).
    #
    # How this matches the project's LLM-based correction goal:
    # - We use OpenRouter at runtime (if configured) for meaning-preserving fluency rewriting.
    # - We keep a fast rule-based baseline so the app stays demo-ready on weak laptops and
    #   gracefully degrades if the API is unavailable.

    fillers: frozenset[str] = frozenset(_FILLERS)

    def rewrite(self, text: str, hints: dict[str, Any] | None = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Input text must be a non-empty string")

        # Hints are currently unused, but kept for API compatibility.
        _ = hints

        # Step 1: normalize whitespace and common stutter patterns that operate on raw text.
        cleaned = normalize_whitespace(text)
        cleaned = _strip_stutter_hyphens(cleaned)
        cleaned = normalize_prolongations(cleaned)

        # Step 2: tokenize into words/numbers and punctuation so we can apply word-level rules.
        tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|\S", cleaned)

        out: list[str] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]

            # Rule: remove filler words (um/uh/er/erm/ah). Do not remove punctuation.
            if _is_word_token(tok) and tok.lower() in self.fillers:
                i += 1
                # If we removed a filler that was surrounded by commas, avoid leaving ', ,'.
                if out and out[-1] == "," and i < len(tokens) and tokens[i] == ",":
                    i += 1
                continue

            # Rule: collapse broken-word lead-ins like "t t to" -> "to".
            # We detect repeated single-letter tokens followed by a word that starts with that letter.
            if _is_word_token(tok) and len(tok) == 1 and tok.isalpha():
                letter = tok.lower()
                j = i
                while j < len(tokens) and _is_word_token(tokens[j]) and tokens[j].isalpha() and len(tokens[j]) == 1:
                    if tokens[j].lower() != letter:
                        break
                    j += 1
                if j > i and j < len(tokens) and _is_word_token(tokens[j]):
                    next_word = tokens[j]
                    if next_word[:1].lower() == letter and len(next_word) > 1:
                        i = j
                        tok = tokens[i]

            # Rule: collapse immediate word repetitions: "I I I" -> "I".
            if _is_word_token(tok) and out:
                prev_word = out[-1]
                if _is_word_token(prev_word) and prev_word.lower() == tok.lower():
                    i += 1
                    continue

            out.append(tok)
            i += 1

        # Step 3: join tokens back and re-normalize. Run prolongation normalization again
        # defensively in case a token slipped through unchanged.
        fluent = normalize_whitespace(normalize_prolongations(_join_tokens(out)))
        return fluent


def rewrite_text(text: str, hints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Service wrapper for the /rewrite and /pipeline endpoints."""

    rewriter = FluencyRewriter()

    # Always keep a deterministic baseline (also used as fallback on API failures).
    baseline = rewriter.rewrite(text=text, hints=hints)

    # Optional pre-normalization before the LLM call (cheap + reduces tokens).
    llm_input = _pre_normalize_for_llm(text)

    api_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key.strip():
        return {
            "original": text,
            "fluent": baseline,
            "engine": "rule-based",
            "llm_used": False,
            "llm_reason": "missing_api_key",
        }

    configured_model = (os.getenv("OPENROUTER_MODEL") or "").strip()
    candidate_models = [configured_model] if configured_model else list(_DEFAULT_OPENROUTER_MODELS)

    last_error = ""
    for model in candidate_models:
        try:
            fluent = _openrouter_llm_rewrite(text=llm_input, api_key=api_key, model=model)
            if fluent:
                return {
                    "original": text,
                    "fluent": fluent,
                    "engine": "openrouter",
                    "llm_used": True,
                    "llm_model": model,
                }
            last_error = "empty_llm_response"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    # Graceful fallback if OpenRouter is down, slow, rate-limited, or model IDs are unavailable.
    return {
        "original": text,
        "fluent": baseline,
        "engine": "rule-based",
        "llm_used": False,
        "llm_reason": last_error or "llm_unavailable",
    }
