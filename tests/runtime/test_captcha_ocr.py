from __future__ import annotations

import ctypes
from pathlib import Path

import pytest

import weconduct.runtime.engine as runtime_engine
from weconduct.builtin_components import get_graph_node_draft_definition
from weconduct.runtime.captcha_ocr import (
    CaptchaOcrDetailedResult,
    CaptchaOcrRecognizer,
    OcrResult,
    _iter_default_captcha_ocr_roots,
)
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_captcha_ocr_default_roots_do_not_include_current_working_directory() -> None:
    assert Path.cwd() / "captcha_ocr" not in _iter_default_captcha_ocr_roots()


def test_recognize_detailed_from_bytes_parses_character_metadata() -> None:
    recognizer = CaptchaOcrRecognizer.__new__(CaptchaOcrRecognizer)
    metadata = (
        b'[{"char":"A","confidence":0.9521,'
        b'"candidates":[{"char":"4","confidence":0.0312}],'
        b'"colors":[{"r":220,"g":40,"b":40}]}]'
    )
    result = OcrResult(b"A", ctypes.c_float(0.9521), metadata, 0)
    result_ptr = ctypes.pointer(result)

    class FakeLibrary:
        def ocr_predict(self, handle: object, buffer: object, length: object) -> object:
            return result_ptr

        def ocr_free_result(self, pointer: object) -> None:
            assert pointer is result_ptr

    recognizer._handle = object()
    recognizer._lib = FakeLibrary()

    detailed = recognizer.recognize_detailed_from_bytes(b"image")

    assert detailed.text == "A"
    assert detailed.confidence == pytest.approx(0.9521)
    assert detailed.character_metadata == [
        {
            "char": "A",
            "confidence": pytest.approx(0.9521),
            "candidates": [{"char": "4", "confidence": pytest.approx(0.0312)}],
            "colors": [{"r": 220, "g": 40, "b": 40}],
        }
    ]


def test_recognize_captcha_exposes_character_metadata_to_variables_and_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeRecognizer:
        def recognize_detailed_from_bytes(self, image_bytes: bytes) -> CaptchaOcrDetailedResult:
            assert image_bytes == b"image"
            return CaptchaOcrDetailedResult(
                text="A",
                confidence=0.9521,
                character_metadata=[
                    {
                        "char": "A",
                        "confidence": 0.9521,
                        "candidates": [{"char": "4", "confidence": 0.0312}],
                        "colors": [{"r": 220, "g": 40, "b": 40}],
                    }
                ],
            )

        def close(self) -> None:
            return None

    def create_recognizer(**kwargs: object) -> FakeRecognizer:
        captured_kwargs.update(kwargs)
        return FakeRecognizer()

    monkeypatch.setattr(runtime_engine, "create_captcha_ocr_recognizer", create_recognizer)
    context = RuntimeContext()

    result = RuntimeExecutorRegistry()._execute_browser_recognize_captcha(
        {
            "node_id": "captcha-1",
            "node_config": {
                "image_bytes_base64": "aW1hZ2U=",
                "target_variable": "captcha_text",
                "metadata_variable": "captcha_characters",
                "confidence_variable": "captcha_confidence",
                "enable_char_meta": True,
                "candidate_count": 2,
            },
        },
        context,
    )

    assert captured_kwargs == {
        "model_name": "common_old.onnx",
        "runtime_root": None,
        "enable_char_meta": True,
        "candidate_count": 2,
    }
    assert context.variables == {
        "captcha_text": "A",
        "captcha_confidence": pytest.approx(0.9521),
        "captcha_characters": result["character_metadata"],
    }
    assert result == {
        "status": "succeeded",
        "node_id": "captcha-1",
        "text": "A",
        "confidence": pytest.approx(0.9521),
        "character_metadata": [
            {
                "char": "A",
                "confidence": 0.9521,
                "candidates": [{"char": "4", "confidence": 0.0312}],
                "colors": [{"r": 220, "g": 40, "b": 40}],
            }
        ],
        "target_variable": "captcha_text",
        "model_name": "common_old.onnx",
        "backend": "captcha_ocr",
    }


def test_recognize_captcha_draft_declares_detailed_result_outputs() -> None:
    draft = get_graph_node_draft_definition("browser.recognize_captcha")

    assert draft is not None
    data_outputs = {
        port["semantic_slot"]: port["port_id"]
        for port in draft["ports"]
        if port["direction"] == "output" and port["relation_layer"] == "data"
    }
    assert data_outputs == {
        "out.text": "out:text",
        "out.confidence": "out:confidence",
        "out.character_metadata": "out:character_metadata",
    }
    assert draft["node_config"] == {
        "selector": "",
        "image_bytes_base64": "",
        "target_variable": "",
        "metadata_variable": "",
        "confidence_variable": "",
        "model_name": "",
        "runtime_root": "",
        "enable_char_meta": True,
        "candidate_count": 3,
    }
