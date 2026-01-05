from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fluencygpt.utils.text import normalize_whitespace


# Filler words commonly present in ASR transcripts.
_FILLERS = {"um", "uh", "er", "erm", "ah"}


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
    """Deterministic, explainable rewriting for offline demos.

    Architecture note:
    The project is structured so the rewrite step could be swapped to an LLM-based
    implementation (same service / endpoints). For a live demo, we use a rule-based
    rewriter because the environment has no API credits and cannot run local LLMs.
    """

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
    fluent = rewriter.rewrite(text=text, hints=hints)
    return {"original": text, "fluent": fluent}
