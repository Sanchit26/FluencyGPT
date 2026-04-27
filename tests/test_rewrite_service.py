import pytest

from fluencygpt.services.rewrite_service import FluencyRewriter, rewrite_text


def test_rewrite_rejects_empty_input():
    with pytest.raises(ValueError):
        rewrite_text("   ")


def test_rewrite_collapses_repetitions_and_fillers():
    rewriter = FluencyRewriter()
    assert rewriter.rewrite("I I I want to um go") == "I want to go"


def test_rewrite_collapses_broken_words():
    rewriter = FluencyRewriter()
    assert rewriter.rewrite("I want t t to go home") == "I want to go home"


def test_rewrite_normalizes_prolongations():
    rewriter = FluencyRewriter()
    assert rewriter.rewrite("wwwhat is thhhis") == "what is this"


def test_rewrite_removes_fillers_and_normalizes_words():
    rewriter = FluencyRewriter()
    assert rewriter.rewrite("I um um really reallly want it") == "I really want it"


def test_rewrite_uses_llm_when_api_key_present(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    def _fake_llm(*, text, api_key, model):  # noqa: ANN001
        _ = text, api_key, model
        return "I want to go home"

    monkeypatch.setattr("fluencygpt.services.rewrite_service._openrouter_llm_rewrite", _fake_llm)

    out = rewrite_text("I I I want to um go home")
    assert out["llm_used"] is True
    assert out["engine"] == "openrouter"
    assert out["fluent"] == "I want to go home"


def test_rewrite_fallback_reports_reason(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "not-a-real-model")

    def _fake_llm_fail(*, text, api_key, model):  # noqa: ANN001
        _ = text, api_key, model
        raise RuntimeError("OpenRouter HTTP error: 404")

    monkeypatch.setattr("fluencygpt.services.rewrite_service._openrouter_llm_rewrite", _fake_llm_fail)

    out = rewrite_text("I I I want to um go home")
    assert out["llm_used"] is False
    assert out["engine"] == "rule-based"
    assert "OpenRouter HTTP error" in out["llm_reason"]
