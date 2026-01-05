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
