from __future__ import annotations

from pathlib import Path

from weconduct.runtime.captcha_ocr import _iter_default_captcha_ocr_roots


def test_captcha_ocr_default_roots_do_not_include_current_working_directory() -> None:
    assert Path.cwd() / "captcha_ocr" not in _iter_default_captcha_ocr_roots()
