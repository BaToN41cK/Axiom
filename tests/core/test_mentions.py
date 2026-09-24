"""``@mention`` expansion tests (``axiom.core.mentions``)."""

from __future__ import annotations

from pathlib import Path

from axiom.core.mentions import expand_mentions, mentioned_files


def test_existing_file_is_expanded(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    out = expand_mentions("look at @src/app.py please", tmp_path)
    assert "print('hi')" in out
    assert "```py" in out


def test_missing_path_stays_text(tmp_path: Path):
    out = expand_mentions("mail me at user@example.com", tmp_path)
    assert out == "mail me at user@example.com"


def test_path_escape_is_ignored(tmp_path: Path):
    out = expand_mentions("sneaky @../secrets.txt", tmp_path)
    assert out == "sneaky @../secrets.txt"


def test_no_workspace_leaves_text_untouched(tmp_path: Path):
    assert expand_mentions("@a/b.py", None) == "@a/b.py"


def test_non_text_suffix_not_expanded(tmp_path: Path):
    (tmp_path / "img.png").write_bytes(b"\x89PNG")
    assert expand_mentions("@img.png", tmp_path) == "@img.png"


def test_mentioned_files_returns_only_valid_workspace_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("app", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside", encoding="utf-8")
    assert mentioned_files("fix @src/app.py and @../outside.py", tmp_path) == ["src/app.py"]


def test_mentioned_files_deduplicates_and_respects_limit(tmp_path: Path):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    assert mentioned_files("@a.py @a.py @b.py @c.py", tmp_path, limit=2) == ["a.py", "b.py"]


def test_mention_only_expansion_keeps_original_text_stored(tmp_path: Path):
    """The stored user text must not change — expansion is model-facing only."""
    (tmp_path / "note.md").write_text("secret plan\n", encoding="utf-8")
    text = "read @note.md now"
    expanded = expand_mentions(text, tmp_path)
    assert "secret plan" in expanded
    assert text == "read @note.md now"  # original untouched
