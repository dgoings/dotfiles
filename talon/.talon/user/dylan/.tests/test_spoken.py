import pytest

from core.spoken import SpokenFormatError, fallback_sections, parse_sections
from core.store import Section

GOOD = '{"sections": [{"title": "Browser", "text": "I fixed it."}]}'


def test_parse_plain_json():
    assert parse_sections(GOOD) == [Section("Browser", "I fixed it.")]


def test_parse_fenced_json_with_prose():
    raw = "Here you go:\n```json\n" + GOOD + "\n```\nHope that helps."
    assert parse_sections(raw) == [Section("Browser", "I fixed it.")]


def test_parse_prose_without_fence():
    assert parse_sections("Sure! " + GOOD + " Done.") == [Section("Browser", "I fixed it.")]


def test_parse_rejects_empty_list():
    with pytest.raises(SpokenFormatError):
        parse_sections('{"sections": []}')


def test_parse_rejects_garbage():
    with pytest.raises(SpokenFormatError):
        parse_sections("not json at all")


def test_parse_rejects_empty_text():
    with pytest.raises(SpokenFormatError):
        parse_sections('{"sections": [{"title": "A", "text": "  "}]}')


def test_fallback_splits_on_headings():
    body = " ".join(["word"] * 70)
    md = f"## One\nAlpha text. {body}\n## Two\nBeta text. {body}"
    out = fallback_sections(md)
    assert [s.title for s in out] == ["One", "Two"]


def test_fallback_strips_markdown_and_code():
    md = (
        "# Title\nSome **bold** and `code` and [link](http://x.com/y).\n\n"
        "```py\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    out = fallback_sections(md)
    text = " ".join(s.text for s in out)
    for ch in "`|*#":
        assert ch not in text
    assert "it's on screen" in text
    assert "http" not in text
    assert "link" in text


def test_fallback_merges_short_paragraphs():
    out = fallback_sections("One short.\n\nTwo short.\n\nThree short.")
    assert len(out) == 1


def test_fallback_empty_input_gives_nothing_or_one():
    assert fallback_sections("") == []
