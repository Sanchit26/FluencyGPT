from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fluencygpt.utils.text import normalize_whitespace


@dataclass(frozen=True)
class Token:
    """A lightweight token with character offsets into the cleaned text.

    We keep this explicit so the detector is explainable and easy to debug.
    Offsets are 0-based indices in the *cleaned* text returned by the detector.
    """

    text: str
    start: int
    end: int

    @property
    def lower(self) -> str:
        return self.text.lower()

    @property
    def is_single_letter(self) -> bool:
        return len(self.text) == 1 and self.text.isalpha()


# Tokenization: words only (letters + apostrophes). We do not include punctuation
# tokens because the required disfluencies in this project are word-based.
WORD_TOKEN_PATTERN = re.compile(r"[A-Za-z']+")


# Rule: prolonged sounds within a token: repeated character 3+ times.
REPEAT_CHAR_PATTERN = re.compile(r"([A-Za-z])\1{2,}")


# Rule: hyphenated broken words: "b-b-because", "t-t-to"
HYPHEN_BROKEN_WORD_PATTERN = re.compile(
    r"\b(?P<c>[A-Za-z])(?:-\1){1,}(?P<rest>[A-Za-z']*)\b",
    flags=re.IGNORECASE,
)


# Fillers: keep this list explicit and editable for debugging.
FILLERS = {
    "uh",
    "um",
    "er",
    "erm",
}


def _tokenize_words(text: str) -> list[Token]:
    """Tokenize into word tokens with spans.

    Example:
      "I I want" -> [Token("I",0,1), Token("I",2,3), Token("want",4,8)]
    """

    tokens: list[Token] = []
    for match in WORD_TOKEN_PATTERN.finditer(text):
        tokens.append(Token(text=match.group(0), start=match.start(), end=match.end()))
    return tokens


def _add_segment(
    out: list[dict[str, Any]],
    *,
    seg_type: str,
    subtype: str,
    start: int,
    end: int,
    text: str,
    confidence: float,
    meta: dict[str, Any] | None = None,
) -> None:
    out.append(
        {
            "type": seg_type,
            "subtype": subtype,
            "start": start,
            "end": end,
            "text": text,
            "confidence": confidence,
            "meta": meta or {},
        }
    )


def detect_disfluencies(text: str, *, include_debug: bool = False) -> dict[str, Any]:
    """Detect disfluencies in ASR-like text using regex + token logic (rule-based).

    Required detections:
    - Word repetitions:     "I I I", "want want"
    - Broken words:         "t t to", "g g go" (spaced) and "b-b-because" (hyphenated)
    - Prolonged sounds:     "ssssorry", "soooo"
    - Fillers:              "uh", "um", "er"

    Returns:
    - cleaned_text: whitespace-normalized intermediate text (no meaning removed)
    - segments: list of structured spans with types/subtypes/metadata
    - summary: counts by type

    Explainability / debug:
    - Set include_debug=True to also return word tokens and which rule matched.
    """

    cleaned = normalize_whitespace(text)
    tokens = _tokenize_words(cleaned)

    segments: list[dict[str, Any]] = []
    debug_hits: list[dict[str, Any]] = []

    # 1) Fillers (token-based: exact match)
    for tok in tokens:
        if tok.lower in FILLERS:
            _add_segment(
                segments,
                seg_type="filler",
                subtype="filler_word",
                start=tok.start,
                end=tok.end,
                text=cleaned[tok.start : tok.end],
                confidence=0.75,
                meta={"token": tok.text},
            )
            if include_debug:
                debug_hits.append({"rule": "filler", "token": tok.text, "span": [tok.start, tok.end]})

    # 2) Word repetitions: consecutive identical word tokens (case-insensitive)
    i = 0
    while i < len(tokens) - 1:
        if tokens[i].lower == tokens[i + 1].lower:
            j = i + 1
            while j < len(tokens) and tokens[j].lower == tokens[i].lower:
                j += 1

            start = tokens[i].start
            end = tokens[j - 1].end
            repeated_word = tokens[i].text
            count = j - i

            _add_segment(
                segments,
                seg_type="word_repetition",
                subtype="consecutive_word_repeat",
                start=start,
                end=end,
                text=cleaned[start:end],
                confidence=0.88,
                meta={"word": repeated_word, "count": count},
            )
            if include_debug:
                debug_hits.append(
                    {
                        "rule": "word_repetition",
                        "word": repeated_word,
                        "count": count,
                        "token_indices": [i, j - 1],
                        "span": [start, end],
                    }
                )

            i = j
        else:
            i += 1

    # 3) Broken words (spaced single-letter repetitions): "t t to", "g g go"
    # Logic:
    # - Find runs of >=2 single-letter tokens with same letter
    # - If the next token starts with that letter, treat as a broken word segment
    i = 0
    while i < len(tokens) - 2:
        t0 = tokens[i]
        if not t0.is_single_letter:
            i += 1
            continue

        letter = t0.lower
        j = i + 1
        while j < len(tokens) and tokens[j].is_single_letter and tokens[j].lower == letter:
            j += 1

        run_len = j - i
        if run_len >= 2 and j < len(tokens):
            next_tok = tokens[j]
            if len(next_tok.text) >= 2 and next_tok.lower.startswith(letter):
                start = tokens[i].start
                end = next_tok.end
                _add_segment(
                    segments,
                    seg_type="broken_word",
                    subtype="spaced_letter_repetition",
                    start=start,
                    end=end,
                    text=cleaned[start:end],
                    confidence=0.84,
                    meta={
                        "letter": letter,
                        "repeats": run_len,
                        "target_word": next_tok.text,
                        "example_join": "-".join([letter] * run_len + [next_tok.text]),
                    },
                )
                if include_debug:
                    debug_hits.append(
                        {
                            "rule": "broken_word_spaced",
                            "letter": letter,
                            "run_len": run_len,
                            "next": next_tok.text,
                            "token_indices": [i, j],
                            "span": [start, end],
                        }
                    )

                i = j + 1
                continue

        i = j

    # 4) Broken words (hyphenated): regex directly over cleaned text.
    for match in HYPHEN_BROKEN_WORD_PATTERN.finditer(cleaned):
        start, end = match.start(), match.end()
        letter = (match.group("c") or "").lower()
        rest = match.group("rest") or ""

        # Estimate repeats count from hyphen sequence: "b-b-because" has 2 hyphens but 3 letters.
        # We compute it from the matched text prefix split.
        prefix = cleaned[start:end]
        repeats = prefix.lower().split("-")
        repeats_count = sum(1 for part in repeats[:-1] if part == letter) + 1

        _add_segment(
            segments,
            seg_type="broken_word",
            subtype="hyphenated_letter_repetition",
            start=start,
            end=end,
            text=cleaned[start:end],
            confidence=0.82,
            meta={"letter": letter, "repeats": repeats_count, "rest": rest},
        )
        if include_debug:
            debug_hits.append(
                {
                    "rule": "broken_word_hyphen",
                    "match": cleaned[start:end],
                    "span": [start, end],
                }
            )

    # 5) Prolonged sounds: locate repeated-character runs within each word token.
    # We return precise subspans (inside the token) so the UI can highlight the exact prolongation.
    for tok in tokens:
        for m in REPEAT_CHAR_PATTERN.finditer(tok.text):
            start = tok.start + m.start()
            end = tok.start + m.end()
            repeated_char = m.group(1)
            repeat_len = m.end() - m.start()

            _add_segment(
                segments,
                seg_type="prolongation",
                subtype="character_prolongation",
                start=start,
                end=end,
                text=cleaned[start:end],
                confidence=0.65,
                meta={"char": repeated_char, "repeat_len": repeat_len, "token": tok.text},
            )
            if include_debug:
                debug_hits.append(
                    {
                        "rule": "prolongation",
                        "token": tok.text,
                        "repeat": cleaned[start:end],
                        "span": [start, end],
                    }
                )

    # Sort: stable, then longer spans first for identical starts.
    segments.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    for idx, seg in enumerate(segments, start=1):
        seg["id"] = idx

    summary: dict[str, int] = {}
    for seg in segments:
        summary[seg["type"]] = summary.get(seg["type"], 0) + 1

    out: dict[str, Any] = {
        "input_text": text,
        "cleaned_text": cleaned,
        "segments": segments,
        "summary": summary,
    }

    if include_debug:
        out["debug"] = {
            "tokens": [{"text": t.text, "start": t.start, "end": t.end} for t in tokens],
            "hits": debug_hits,
        }

    return out
