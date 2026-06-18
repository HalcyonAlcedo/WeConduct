from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_CAPTCHA_OCR_MODEL = "common_old.onnx"


class CaptchaOcrRuntimeUnavailable(RuntimeError):
    pass


class OcrConfig(ctypes.Structure):
    _fields_ = [
        ("threads", ctypes.c_uint16),
        ("warmup", ctypes.c_bool),
        ("log_level", ctypes.c_char_p),
        ("input_width", ctypes.c_uint32),
        ("input_height", ctypes.c_uint32),
        ("confidence_threshold", ctypes.c_float),
    ]


class OcrResult(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("confidence", ctypes.c_float),
        ("error_code", ctypes.c_int32),
    ]


class CaptchaOcrRecognizer:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_CAPTCHA_OCR_MODEL,
        runtime_root: str | Path | None = None,
    ) -> None:
        self.runtime_root = _resolve_captcha_ocr_runtime(runtime_root)
        self.model_name = model_name or DEFAULT_CAPTCHA_OCR_MODEL
        self.model_path = _resolve_model_path(self.runtime_root, self.model_name)
        _ensure_ort_dylib_path(self.runtime_root)
        dll_path = self.runtime_root / "bin" / "captcha_ocr.dll"
        try:
            self._lib = ctypes.CDLL(str(dll_path))
        except OSError as exc:
            raise CaptchaOcrRuntimeUnavailable(f"captcha_ocr dll load failed: {dll_path}: {exc}") from exc
        self._lib.ocr_init.argtypes = [ctypes.c_char_p, ctypes.POINTER(OcrConfig)]
        self._lib.ocr_init.restype = ctypes.c_void_p
        self._lib.ocr_predict.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        self._lib.ocr_predict.restype = ctypes.POINTER(OcrResult)
        self._lib.ocr_free_result.argtypes = [ctypes.POINTER(OcrResult)]
        self._lib.ocr_free_result.restype = None
        self._lib.ocr_shutdown.argtypes = [ctypes.c_void_p]
        self._lib.ocr_shutdown.restype = None

        input_width, input_height = _suggest_input_size(self.model_name)
        cfg = OcrConfig(
            1,
            False,
            b"warn",
            int(os.environ.get("CAPTCHA_OCR_INPUT_WIDTH", str(input_width))),
            int(os.environ.get("CAPTCHA_OCR_INPUT_HEIGHT", str(input_height))),
            0.5,
        )
        self._handle = self._lib.ocr_init(str(self.model_path).encode("utf-8"), ctypes.byref(cfg))
        if not self._handle:
            raise CaptchaOcrRuntimeUnavailable("captcha_ocr init failed: empty handle")

    def recognize_from_bytes(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        buf = (ctypes.c_uint8 * len(image_bytes)).from_buffer_copy(image_bytes)
        result_ptr = self._lib.ocr_predict(self._handle, buf, ctypes.c_size_t(len(image_bytes)))
        if not result_ptr:
            return ""
        try:
            raw_text = result_ptr.contents.text
            return raw_text.decode("utf-8", errors="ignore").strip() if raw_text else ""
        finally:
            self._lib.ocr_free_result(result_ptr)

    def close(self) -> None:
        if getattr(self, "_handle", None):
            self._lib.ocr_shutdown(self._handle)
            self._handle = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def create_captcha_ocr_recognizer(**kwargs: Any) -> CaptchaOcrRecognizer:
    return CaptchaOcrRecognizer(**kwargs)


def _resolve_captcha_ocr_runtime(runtime_root: str | Path | None) -> Path:
    candidates = []
    if runtime_root is not None:
        candidates.append(Path(runtime_root))
    env_root = os.environ.get("WECONDUCT_CAPTCHA_OCR_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(_iter_default_captcha_ocr_roots())
    for root in candidates:
        root = root.expanduser()
        if (root / "bin" / "captcha_ocr.dll").is_file() and (root / "model").is_dir():
            return root.resolve()
    raise CaptchaOcrRuntimeUnavailable(
        "captcha_ocr runtime not found; set WECONDUCT_CAPTCHA_OCR_ROOT or place captcha_ocr inside WeConduct"
    )


def _iter_default_captcha_ocr_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.argv[0]).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        roots.extend(
            [
                exe_dir / "captcha_ocr",
                exe_dir / "_internal" / "captcha_ocr",
                meipass / "captcha_ocr",
            ]
        )
    project_root = Path(__file__).resolve().parents[3]
    roots.extend(
        [
            project_root / "third_party" / "captcha_ocr",
            Path.cwd() / "captcha_ocr",
        ]
    )
    return roots


def _resolve_model_path(runtime_root: Path, model_name: str) -> Path:
    raw_model = Path(model_name or DEFAULT_CAPTCHA_OCR_MODEL)
    if raw_model.is_absolute():
        if raw_model.is_file():
            return raw_model
        raise CaptchaOcrRuntimeUnavailable(f"captcha_ocr model not found: {raw_model}")
    for candidate in (runtime_root / "model" / raw_model, runtime_root / raw_model):
        if candidate.is_file():
            return candidate.resolve()
    raise CaptchaOcrRuntimeUnavailable(f"captcha_ocr model not found: {model_name}")


def _ensure_ort_dylib_path(runtime_root: Path) -> None:
    current = os.environ.get("ORT_DYLIB_PATH")
    if current and Path(current).is_file():
        return
    ort_path = runtime_root / "bin" / "onnxruntime.dll"
    if ort_path.is_file():
        os.environ["ORT_DYLIB_PATH"] = str(ort_path.resolve())
        return
    raise CaptchaOcrRuntimeUnavailable(f"onnxruntime.dll not found: {ort_path}")


def _suggest_input_size(model_name: str) -> tuple[int, int]:
    return (160, 64) if (model_name or "").lower() == "common_old.onnx" else (160, 64)
