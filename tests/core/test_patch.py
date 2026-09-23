"""Unit tests for the unified-diff applier (``axiom.core.patch``)."""

from __future__ import annotations

import pytest

from axiom.core.patch import PatchError, apply_unified_diff, extract_target_path


def test_apply_simple_hunk():
    original = "line one\nline two\nline three\n"
    patch = (
        "--- a/file.txt\n+++ b/file.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " line one\n"
        "-line two\n"
        "+line 2 (edited)\n"
        " line three\n"
    )
    out = apply_unified_diff(original, patch)
    assert out == "line one\nline 2 (edited)\nline three\n"


def test_apply_new_file_from_dev_null():
    original = ""
    patch = (
        "--- /dev/null\n+++ b/new.txt\n"
        "@@ -0,0 +1,2 @@\n"
        "+alpha\n"
        "+beta\n"
    )
    out = apply_unified_diff(original, patch)
    assert out == "alpha\nbeta"


def test_context_mismatch_is_rejected():
    original = "aaa\nbbb\nccc\n"
    patch = (
        "--- a/f\n+++ b/f\n"
        "@@ -1,3 +1,3 @@\n"
        " aaa\n"
        "-WRONG\n"
        "+xxx\n"
        " ccc\n"
    )
    with pytest.raises(PatchError, match="Context mismatch"):
        apply_unified_diff(original, patch)


def test_patch_without_hunks_is_rejected():
    with pytest.raises(PatchError, match="no hunks"):
        apply_unified_diff("x\n", "--- a/f\n+++ b/f\n")


def test_extract_target_path():
    patch = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert extract_target_path(patch) == "src/main.py"
    assert extract_target_path("--- /dev/null\n+++ /dev/null\n") is None
