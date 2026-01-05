from fluencygpt.services.disfluency_service import detect_disfluencies


def test_detects_required_disfluencies():
    text = "I I I want to um go to the ssssorry store and g g go home"
    out = detect_disfluencies(text)

    assert out["cleaned_text"]
    types = [s["type"] for s in out["segments"]]

    assert "word_repetition" in types
    assert "filler" in types
    assert "prolongation" in types
    assert "broken_word" in types


def test_spaced_broken_word_span_contains_target_word():
    text = "t t to the park"
    out = detect_disfluencies(text)

    broken = [s for s in out["segments"] if s["type"] == "broken_word" and s["subtype"] == "spaced_letter_repetition"]
    assert broken
    assert "to" in broken[0]["text"].lower()


def test_debug_contains_tokens_and_hits():
    text = "want want um"
    out = detect_disfluencies(text, include_debug=True)

    assert "debug" in out
    assert "tokens" in out["debug"]
    assert "hits" in out["debug"]
