#!/usr/bin/env python3
"""Tests for context.select_copy() — variant selection logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import context as _ctx

# ── Fixtures ──────────────────────────────────────────────────────────────────

BASE_AD = {
    "id": "ad_test",
    "text": "default text",
    "url": "https://example.com",
}

VARIANT_AD = {
    **BASE_AD,
    "use_variants": True,
    "copy_variants": {
        "default":    "default variant text",
        "typescript": "typescript variant text",
        "python":     "python variant text",
        "rust":       "rust variant text",
        "go":         "go variant text",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
        return True
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        return False


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_variants_returns_text_and_default():
    text, variant = _ctx.select_copy(BASE_AD, {"typescript"})
    assert text == "default text", f"got {text!r}"
    assert variant == "default", f"got {variant!r}"

def test_variants_disabled_returns_text_and_default():
    ad = {**VARIANT_AD, "use_variants": False}
    text, variant = _ctx.select_copy(ad, {"typescript"})
    assert text == "default text"
    assert variant == "default"

def test_typescript_context_selects_typescript_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, {"typescript"})
    assert text == "typescript variant text"
    assert variant == "typescript"

def test_python_context_selects_python_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, {"python"})
    assert text == "python variant text"
    assert variant == "python"

def test_rust_context_selects_rust_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, {"rust"})
    assert text == "rust variant text"
    assert variant == "rust"

def test_go_context_selects_go_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, {"go"})
    assert text == "go variant text"
    assert variant == "go"

def test_empty_context_returns_default_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, set())
    assert text == "default variant text"
    assert variant == "default"

def test_none_context_returns_default_variant():
    text, variant = _ctx.select_copy(VARIANT_AD, None)
    assert text == "default variant text"
    assert variant == "default"

def test_typescript_beats_python_when_both_present():
    # typescript comes before python in the priority list
    text, variant = _ctx.select_copy(VARIANT_AD, {"typescript", "python"})
    assert variant == "typescript", f"expected typescript, got {variant!r}"

def test_rust_beats_python_when_both_present():
    text, variant = _ctx.select_copy(VARIANT_AD, {"rust", "python"})
    assert variant == "rust", f"expected rust, got {variant!r}"

def test_unknown_tag_falls_back_to_default():
    text, variant = _ctx.select_copy(VARIANT_AD, {"cobol", "fortran"})
    assert text == "default variant text"
    assert variant == "default"

def test_tag_not_in_variants_dict_falls_back_to_default():
    ad = {**VARIANT_AD, "copy_variants": {"typescript": "ts text"}}
    text, variant = _ctx.select_copy(ad, {"python"})
    assert text == "default text"   # falls through to ad["text"]
    assert variant == "default"

def test_missing_default_variant_falls_back_to_ad_text():
    ad = {**VARIANT_AD, "copy_variants": {"typescript": "ts text"}}
    text, variant = _ctx.select_copy(ad, {"typescript"})
    assert text == "ts text"
    assert variant == "typescript"

def test_empty_copy_variants_dict_returns_ad_text():
    ad = {**BASE_AD, "use_variants": True, "copy_variants": {}}
    text, variant = _ctx.select_copy(ad, {"typescript"})
    assert text == "default text"
    assert variant == "default"

def test_ad_without_use_variants_key_returns_ad_text():
    ad = {**BASE_AD, "copy_variants": {"typescript": "ts text"}}
    text, variant = _ctx.select_copy(ad, {"typescript"})
    assert text == "default text"
    assert variant == "default"


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("no variants → text + default key",        test_no_variants_returns_text_and_default),
        ("use_variants=False → text + default key",  test_variants_disabled_returns_text_and_default),
        ("typescript context → typescript variant",  test_typescript_context_selects_typescript_variant),
        ("python context → python variant",          test_python_context_selects_python_variant),
        ("rust context → rust variant",              test_rust_context_selects_rust_variant),
        ("go context → go variant",                  test_go_context_selects_go_variant),
        ("empty context → default variant",          test_empty_context_returns_default_variant),
        ("None context → default variant",           test_none_context_returns_default_variant),
        ("typescript beats python (priority)",       test_typescript_beats_python_when_both_present),
        ("rust beats python (priority)",             test_rust_beats_python_when_both_present),
        ("unknown tag → default fallback",           test_unknown_tag_falls_back_to_default),
        ("tag not in variants → default fallback",   test_tag_not_in_variants_dict_falls_back_to_default),
        ("no default key → ad text fallback",        test_missing_default_variant_falls_back_to_ad_text),
        ("empty copy_variants → ad text",            test_empty_copy_variants_dict_returns_ad_text),
        ("missing use_variants key → ad text",       test_ad_without_use_variants_key_returns_ad_text),
    ]

    print(f"\ntest_copy_variants.py — {len(tests)} tests\n")
    results = [run(name, fn) for name, fn in tests]
    passed  = sum(results)
    failed  = len(results) - passed
    print(f"\n{passed}/{len(results)} PASS", "✓" if not failed else f"  {failed} FAIL")
    sys.exit(0 if not failed else 1)
