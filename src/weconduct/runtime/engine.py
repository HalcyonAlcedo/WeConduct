from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import re
import ast
from time import monotonic
import urllib.error
import urllib.parse
import urllib.request
from zipfile import BadZipFile
from typing import Any
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from playwright.sync_api import Browser, Frame, Page, Playwright, sync_playwright
from weconduct.runtime.captcha_ocr import (
    DEFAULT_CAPTCHA_OCR_MODEL,
    CaptchaOcrRuntimeUnavailable,
    create_captcha_ocr_recognizer,
)


@dataclass
class RuntimeContext:
    variables: dict = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    browser_runtime: dict[str, Any] = field(default_factory=dict)
    flow_runtime: dict[str, Any] = field(default_factory=dict)
    project_directory: Path | None = None
    workspace_root: Path | None = None

    def close(self) -> None:
        browser = self.browser_runtime.get("browser")
        playwright = self.browser_runtime.get("playwright")
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        self.browser_runtime.clear()


class RuntimeExecutorRegistry:
    def __init__(self, *, runtime_settings: dict | None = None) -> None:
        self._runtime_settings = runtime_settings or {}
        self._executors = {
            "flow.start": self._execute_flow_start,
            "http.request": self._execute_http_request,
            "browser.navigate": self._execute_browser_navigate,
            "browser.fill": self._execute_browser_fill,
            "browser.click": self._execute_browser_click,
            "browser.hover": self._execute_browser_hover,
            "browser.select_option": self._execute_browser_select_option,
            "browser.wait_for_element": self._execute_browser_wait_for_element,
            "browser.wait_for_navigation": self._execute_browser_wait_for_navigation,
            "browser.wait_for_timeout": self._execute_browser_wait_for_timeout,
            "browser.screenshot": self._execute_browser_screenshot,
            "browser.recognize_captcha": self._execute_browser_recognize_captcha,
            "browser.extract_web_table": self._execute_browser_extract_web_table,
            "browser.extract_web_table_to_excel": self._execute_browser_extract_web_table_to_excel,
            "browser.inject_js": self._execute_browser_inject_js,
            "browser.run_js": self._execute_browser_run_js,
            "browser.switch_to_frame": self._execute_browser_switch_to_frame,
            "browser.switch_to_parent_frame": self._execute_browser_switch_to_parent_frame,
            "browser.switch_to_default_content": self._execute_browser_switch_to_default_content,
            "browser.open_frame_page": self._execute_browser_open_frame_page,
            "data.map": self._execute_data_map,
            "data.set_variable": self._execute_set_variable,
            "data.get_variable": self._execute_get_variable,
            "data.get_text": self._execute_get_text,
            "data.get_attribute": self._execute_get_attribute,
            "data.get_value": self._execute_get_value,
            "data.get_element_count": self._execute_get_element_count,
            "data.set_variables_batch": self._execute_set_variables_batch,
            "data.increment_variable": self._execute_increment_variable,
            "data.decrement_variable": self._execute_decrement_variable,
            "data.create_list": self._execute_create_list,
            "data.list_append": self._execute_list_append,
            "data.list_extend": self._execute_list_extend,
            "data.list_get": self._execute_list_get,
            "data.list_set": self._execute_list_set,
            "data.list_index": self._execute_list_index,
            "data.list_length": self._execute_list_length,
            "data.list_insert": self._execute_list_insert,
            "data.list_remove": self._execute_list_remove,
            "data.list_slice": self._execute_list_slice,
            "data.list_sort": self._execute_list_sort,
            "data.list_reverse": self._execute_list_reverse,
            "data.evaluate_expression": self._execute_evaluate_expression,
            "data.regex_replace": self._execute_regex_replace,
            "file.write_text_file": self._execute_write_text_file,
            "file.read_text_file": self._execute_read_text_file,
            "file.read_csv_cell": self._execute_read_csv_cell,
            "file.read_csv_row": self._execute_read_csv_row,
            "file.read_csv_table": self._execute_read_csv_table,
            "excel.write_cell": self._execute_write_excel_cell,
            "excel.write_row": self._execute_write_excel_row,
            "excel.write_table": self._execute_write_excel_table,
            "excel.write_file": self._execute_write_excel_file,
            "excel.update_cells": self._execute_update_excel_cells,
            "excel.update_batch": self._execute_update_excel_batch,
            "excel.read_cell": self._execute_read_excel_cell,
            "excel.read_row": self._execute_read_excel_row,
            "excel.read_table": self._execute_read_excel_table,
            "python.run": self._execute_python_run,
            "control.foreach": self._execute_control_foreach,
            "control.jump_to_step": self._execute_control_jump_to_step,
            "control.end_foreach": self._execute_control_end_foreach,
            "control.foreach_continue": self._execute_control_foreach_continue,
            "control.foreach_break": self._execute_control_foreach_break,
            "session.apply_auth_session": self._execute_session_apply_auth_session,
            "dialog.switch_dialog_mode": self._execute_dialog_switch_dialog_mode,
            "dialog.watch_dialogs": self._execute_dialog_watch_dialogs,
            "dialog.handle_dialogs": self._execute_dialog_handle_dialogs,
            "dialog.set_agent_config": self._execute_dialog_set_agent_config,
        }

    def execute(self, node_kind: str | None, node: dict, context: RuntimeContext) -> dict:
        if not isinstance(node_kind, str) or node_kind not in self._executors:
            return {
                "status": "succeeded",
                "node_id": node["node_id"],
                "executor": "noop",
            }
        return self._executors[node_kind](node, context)

    def _execute_flow_start(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        initial_variables = node_config.get("initial_variables")
        if not isinstance(initial_variables, dict):
            initial_variables = {}
        for key, value in initial_variables.items():
            if isinstance(key, str) and key.strip():
                context.variables[key.strip()] = _resolve_value(value, context)
        browser_config = _resolve_browser_launch_config(node_config.get("browser_config"), context)
        if browser_config:
            context.browser_runtime["launch_options"] = dict(browser_config)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "initial_variable_count": len(initial_variables),
            "initial_variable_names": [
                key.strip()
                for key in initial_variables
                if isinstance(key, str) and key.strip()
            ],
            "browser_config": browser_config,
        }

    def _execute_http_request(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        if not self._is_local_network_access_allowed():
            return _failed_result(
                node,
                "http.local_network_disabled",
                "local network access is disabled",
            )
        method = str(_resolve_value(node_config.get("method", "GET"), context)).upper()
        url = _resolve_value(node_config.get("url"), context)
        if not isinstance(url, str) or not url.strip():
            return _failed_result(node, "http.url_required", "http.request requires node_config.url")

        headers = _resolve_value(node_config.get("headers", {}), context)
        if not isinstance(headers, dict):
            return _failed_result(node, "http.headers_invalid", "node_config.headers must be an object")

        timeout_value = _resolve_value(node_config.get("timeout", 30), context)
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            return _failed_result(node, "http.timeout_invalid", "node_config.timeout must be numeric")

        body_value = _resolve_value(node_config.get("body"), context)
        request_body = None
        request_headers = {str(key): str(value) for key, value in headers.items()}
        if body_value is not None:
            if isinstance(body_value, (dict, list)):
                request_body = json.dumps(body_value).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
            elif isinstance(body_value, bytes):
                request_body = body_value
            else:
                request_body = str(body_value).encode("utf-8")

        try:
            request = urllib.request.Request(
                url,
                data=request_body,
                headers=request_headers,
                method=method,
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw_body = response.read()
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                response_body = _decode_http_body(raw_body, response_headers)
                result = {
                    "status": "succeeded",
                    "node_id": node["node_id"],
                    "method": method,
                    "url": url,
                    "status_code": response.status,
                    "headers": response_headers,
                    "body": response_body,
                    "body_text": raw_body.decode("utf-8", errors="replace"),
                }
        except urllib.error.HTTPError as exc:
            raw_body = exc.read()
            result = {
                "status": "failed",
                "node_id": node["node_id"],
                "error_code": "http.status_error",
                "message": f"http request failed with status {exc.code}",
                "method": method,
                "url": url,
                "status_code": exc.code,
                "headers": {key.lower(): value for key, value in exc.headers.items()},
                "body": _decode_http_body(raw_body, dict(exc.headers.items())),
                "body_text": raw_body.decode("utf-8", errors="replace"),
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            result = {
                "status": "failed",
                "node_id": node["node_id"],
                "error_code": "http.request_failed",
                "message": str(exc),
                "method": method,
                "url": url,
            }
        context.variables["last_http_response"] = result
        return result

    def _execute_browser_navigate(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        if not self._is_browser_executor_allowed():
            return _failed_result(node, "browser.executor_disabled", "browser executor is disabled")
        url = _resolve_value(node_config.get("url"), context)
        if not isinstance(url, str) or not url.strip():
            return _failed_result(node, "browser.url_required", "browser.navigate requires node_config.url")
        page = _require_browser_page(context)
        page.goto(url, wait_until="domcontentloaded")
        _reset_browser_frame_context(context)
        title = page.title()
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "page_url": page.url,
            "title": title,
        }
        context.variables["last_browser_url"] = page.url
        return result

    def _execute_browser_fill(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        value = _resolve_value(node_config.get("value"), context)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        if not isinstance(value, str):
            value = "" if value is None else str(value)
        target = _require_browser_target(context)
        target.locator(selector).fill(value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector,
            "value": value,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_click(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        page = _require_browser_page(context)
        target = _require_browser_target(context)
        target.locator(selector).click()
        page.wait_for_load_state("domcontentloaded")
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector,
            "page_url": page.url,
        }

    def _execute_browser_hover(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        target = _require_browser_target(context)
        target.locator(selector).hover()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_select_option(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        value = _resolve_value(node_config.get("value"), context)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        if not isinstance(value, str) or not value.strip():
            return _failed_result(node, "browser.value_required", "select_option requires value")
        target = _require_browser_target(context)
        selected = target.locator(selector).select_option(value=value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector,
            "value": value,
            "selected_values": selected,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_wait_for_element(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        timeout_ms = _resolve_int(_resolve_value(node_config.get("timeout"), context), default=10000)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        target = _require_browser_target(context)
        target.locator(selector).wait_for(state="visible", timeout=timeout_ms)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector,
            "timeout_ms": timeout_ms,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_wait_for_navigation(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        url_pattern = _resolve_value(node_config.get("url_pattern"), context)
        timeout_ms = _resolve_int(_resolve_value(node_config.get("timeout"), context), default=15000)
        if not isinstance(url_pattern, str) or not url_pattern.strip():
            return _failed_result(node, "browser.url_pattern_required", "url_pattern is required")
        target = _require_browser_target(context)
        matched_url = _wait_for_browser_url(target, url_pattern.strip(), timeout_ms)
        if matched_url is None:
            return _failed_result(node, "browser.navigation_timeout", "browser.wait_for_navigation timed out")
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "url_pattern": url_pattern.strip(),
            "matched_url": matched_url,
            "timeout_ms": timeout_ms,
        }

    def _execute_browser_wait_for_timeout(self, node: dict, context: RuntimeContext) -> dict:
        timeout_ms = _resolve_int(_resolve_value(_node_config(node).get("timeout"), context), default=0)
        _require_browser_page(context).wait_for_timeout(timeout_ms)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "timeout_ms": timeout_ms,
        }

    def _execute_browser_screenshot(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        path_value = _resolve_value(node_config.get("path"), context)
        if not isinstance(path_value, str) or not path_value.strip():
            return _failed_result(node, "browser.screenshot_path_required", "screenshot path is required")
        path = _resolve_runtime_path(path_value, context)
        path.parent.mkdir(parents=True, exist_ok=True)
        page = _require_browser_page(context)
        page.screenshot(path=str(path))
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(path.resolve()),
            "bytes_written": path.stat().st_size,
            "page_url": page.url,
        }

    def _execute_browser_inject_js(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        script = _resolve_value(node_config.get("script") or node_config.get("code"), context)
        if not isinstance(script, str) or not script.strip():
            return _failed_result(node, "browser.script_required", "JavaScript script is required")
        target = _require_browser_target(context)
        value = target.evaluate(script)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "script_length": len(script),
            "value": value,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_run_js(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        script = _resolve_value(node_config.get("script") or node_config.get("code"), context)
        if not isinstance(script, str) or not script.strip():
            return _failed_result(node, "browser.script_required", "JavaScript script is required")
        target = _require_browser_target(context)
        value = target.evaluate(script)
        _store_optional_variable(node_config, context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "script_length": len(script),
            "value": value,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_recognize_captcha(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        target_variable = (
            node_config.get("target_variable")
            or node_config.get("variable_name")
            or node_config.get("name")
        )
        if not isinstance(target_variable, str) or not target_variable.strip():
            return _failed_result(
                node,
                "browser.captcha_target_variable_required",
                "target_variable is required",
            )
        model_name = (
            node_config.get("model_name")
            or node_config.get("model")
            or node_config.get("captcha_model")
            or DEFAULT_CAPTCHA_OCR_MODEL
        )
        if not isinstance(model_name, str) or not model_name.strip():
            model_name = DEFAULT_CAPTCHA_OCR_MODEL

        try:
            image_bytes = self._resolve_captcha_image_bytes(node, context)
        except ValueError as exc:
            return _failed_result(node, "browser.captcha_image_invalid", str(exc))

        runtime_root = node_config.get("runtime_root")
        try:
            recognizer = create_captcha_ocr_recognizer(
                model_name=model_name.strip(),
                runtime_root=runtime_root,
            )
            try:
                text = recognizer.recognize_from_bytes(image_bytes)
            finally:
                close = getattr(recognizer, "close", None)
                if callable(close):
                    close()
        except (CaptchaOcrRuntimeUnavailable, RuntimeError) as exc:
            return _failed_result(node, "browser.captcha_ocr_unavailable", str(exc))

        if not text:
            return _failed_result(
                node,
                "browser.captcha_empty_result",
                "captcha_ocr returned an empty result",
            )

        target_variable = target_variable.strip()
        context.variables[target_variable] = text
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "text": text,
            "target_variable": target_variable,
            "model_name": model_name.strip(),
            "backend": "captcha_ocr",
        }

    def _resolve_captcha_image_bytes(self, node: dict, context: RuntimeContext) -> bytes:
        node_config = _node_config(node)
        encoded = _resolve_value(node_config.get("image_bytes_base64"), context)
        if isinstance(encoded, str) and encoded.strip():
            raw_encoded = encoded.split(",", 1)[1] if encoded.startswith("data:") else encoded
            try:
                return base64.b64decode(raw_encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("image_bytes_base64 must be valid base64") from exc

        selector = _resolve_value(node_config.get("selector"), context)
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("selector or image_bytes_base64 is required")
        target = _require_browser_target(context)
        return target.locator(selector.strip()).screenshot()

    def _execute_browser_extract_web_table(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector = _resolve_value(node_config.get("selector"), context)
        if not isinstance(selector, str) or not selector.strip():
            return _failed_result(node, "browser.selector_required", "selector is required")
        target = _require_browser_target(context)
        try:
            table = target.locator(selector.strip()).evaluate(_WEB_TABLE_EXTRACT_SCRIPT)
        except Exception as exc:  # Playwright wraps selector/evaluate failures.
            return _failed_result(node, "browser.web_table_extract_failed", str(exc))
        if not isinstance(table, dict):
            return _failed_result(node, "browser.web_table_invalid", "web table extractor returned invalid data")
        rows = table.get("rows")
        headers = table.get("headers")
        if not isinstance(rows, list) or not isinstance(headers, list):
            return _failed_result(node, "browser.web_table_invalid", "web table rows or headers are invalid")
        _store_optional_variable(node_config, context, rows)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector.strip(),
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
        }

    def _execute_browser_extract_web_table_to_excel(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        table_result = self._execute_browser_extract_web_table(node, context)
        if table_result.get("status") == "failed":
            return table_result
        path_value = _resolve_value(node_config.get("path"), context)
        if not isinstance(path_value, str) or not path_value.strip():
            return _failed_result(node, "excel.path_required", "Excel file path is required")
        sheet_name = _resolve_value(node_config.get("sheet_name", "Sheet1"), context)
        if not isinstance(sheet_name, str) or not sheet_name.strip():
            return _failed_result(node, "excel.sheet_name_required", "Excel sheet_name is required")
        path = _resolve_runtime_path(path_value, context)
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name.strip()
        headers = table_result["headers"]
        rows = table_result["rows"]
        if headers:
            for column_index, header in enumerate(headers, start=1):
                worksheet.cell(row=1, column=column_index, value=header)
            start_row = 2
        else:
            start_row = 1
        for row_offset, row in enumerate(rows, start=start_row):
            values = [row.get(str(header)) for header in headers] if isinstance(row, dict) else list(row)
            for column_index, value in enumerate(values, start=1):
                worksheet.cell(row=row_offset, column=column_index, value=value)
        workbook.save(path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(path.resolve()),
            "sheet_name": sheet_name.strip(),
            "headers": headers,
            "row_count": len(rows),
        }

    def _execute_browser_switch_to_frame(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        frame = _resolve_browser_frame(node_config, context)
        if frame is None:
            return _failed_result(node, "browser.frame_not_found", "target frame was not found")
        frame_stack = context.browser_runtime.setdefault("frame_stack", [])
        frame_stack.append(frame)
        context.browser_runtime["current_frame"] = frame
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "frame_name": frame.name,
            "frame_url": frame.url,
            "frame_depth": len(frame_stack),
        }

    def _execute_browser_switch_to_parent_frame(self, node: dict, context: RuntimeContext) -> dict:
        frame_stack = context.browser_runtime.setdefault("frame_stack", [])
        if frame_stack:
            frame_stack.pop()
        if frame_stack:
            context.browser_runtime["current_frame"] = frame_stack[-1]
        else:
            context.browser_runtime.pop("current_frame", None)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "frame_depth": len(frame_stack),
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_switch_to_default_content(self, node: dict, context: RuntimeContext) -> dict:
        _reset_browser_frame_context(context)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "frame_depth": 0,
            "page_url": _require_browser_page(context).url,
        }

    def _execute_browser_open_frame_page(self, node: dict, context: RuntimeContext) -> dict:
        frame = _resolve_browser_frame(_node_config(node), context)
        if frame is None:
            current_frame = context.browser_runtime.get("current_frame")
            frame = current_frame if isinstance(current_frame, Frame) else None
        if frame is None or not frame.url:
            return _failed_result(node, "browser.frame_not_found", "target frame was not found")
        page = _require_browser_page(context)
        previous_frame_url = frame.url
        page.goto(previous_frame_url, wait_until="domcontentloaded")
        _reset_browser_frame_context(context)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "page_url": page.url,
            "previous_frame_url": previous_frame_url,
        }

    def _execute_data_map(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        source_value = (
            _resolve_value(node_config["source"], context)
            if "source" in node_config
            else None
        )
        upstream = _last_node_output(context)
        if source_value is None:
            source_value = upstream
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "value": source_value,
            "mapped_from_node_id": upstream.get("node_id") if isinstance(upstream, dict) else None,
            "response_status_code": upstream.get("status_code") if isinstance(upstream, dict) else None,
        }
        variable_name = node_config.get("variable_name")
        if isinstance(variable_name, str) and variable_name.strip():
            context.variables[variable_name.strip()] = source_value
        context.variables["last_data_map_result"] = result
        return result

    def _execute_set_variable(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        name = node_config.get("name") or node_config.get("variable_name")
        if not isinstance(name, str) or not name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        value = _resolve_value(node_config.get("value"), context)
        context.variables[name.strip()] = value
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": name.strip(),
            "value": value,
        }

    def _execute_get_variable(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        name = node_config.get("name") or node_config.get("variable_name")
        if not isinstance(name, str) or not name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": name.strip(),
            "value": context.variables.get(name.strip()),
        }

    def _execute_get_text(self, node: dict, context: RuntimeContext) -> dict:
        selector_result = _require_selector(node, context)
        if isinstance(selector_result, dict):
            return selector_result
        value = _require_browser_target(context).locator(selector_result).inner_text()
        _store_optional_variable(_node_config(node), context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector_result,
            "value": value,
        }

    def _execute_get_attribute(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        selector_result = _require_selector(node, context)
        if isinstance(selector_result, dict):
            return selector_result
        attribute = _resolve_value(node_config.get("attribute") or node_config.get("attribute_name"), context)
        if not isinstance(attribute, str) or not attribute.strip():
            return _failed_result(node, "data.attribute_required", "attribute is required")
        value = _require_browser_target(context).locator(selector_result).get_attribute(attribute.strip())
        _store_optional_variable(node_config, context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector_result,
            "attribute": attribute.strip(),
            "value": value,
        }

    def _execute_get_value(self, node: dict, context: RuntimeContext) -> dict:
        selector_result = _require_selector(node, context)
        if isinstance(selector_result, dict):
            return selector_result
        value = _require_browser_target(context).locator(selector_result).input_value()
        _store_optional_variable(_node_config(node), context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector_result,
            "value": value,
        }

    def _execute_get_element_count(self, node: dict, context: RuntimeContext) -> dict:
        selector_result = _require_selector(node, context)
        if isinstance(selector_result, dict):
            return selector_result
        value = _require_browser_target(context).locator(selector_result).count()
        _store_optional_variable(_node_config(node), context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "selector": selector_result,
            "value": value,
        }

    def _execute_set_variables_batch(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        variables = _resolve_value(node_config.get("variables"), context)
        if not isinstance(variables, dict):
            return _failed_result(node, "data.variables_invalid", "variables must be an object")
        variable_names: list[str] = []
        for name, value in variables.items():
            if isinstance(name, str) and name.strip():
                context.variables[name.strip()] = value
                variable_names.append(name.strip())
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_names": variable_names,
            "count": len(variable_names),
        }

    def _execute_increment_variable(self, node: dict, context: RuntimeContext) -> dict:
        return self._execute_numeric_variable_delta(node, context, multiplier=1)

    def _execute_decrement_variable(self, node: dict, context: RuntimeContext) -> dict:
        return self._execute_numeric_variable_delta(node, context, multiplier=-1)

    def _execute_numeric_variable_delta(self, node: dict, context: RuntimeContext, *, multiplier: int) -> dict:
        node_config = _node_config(node)
        variable_name = node_config.get("variable_name") or node_config.get("name")
        if not isinstance(variable_name, str) or not variable_name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        step_value = _resolve_value(node_config.get("step", 1), context)
        current_value = context.variables.get(variable_name.strip(), 0)
        try:
            step = float(step_value)
            current = float(current_value)
        except (TypeError, ValueError):
            return _failed_result(node, "data.numeric_variable_invalid", "current value and step must be numeric")
        value: int | float = current + (step * multiplier)
        if value.is_integer():
            value = int(value)
        context.variables[variable_name.strip()] = value
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name.strip(),
            "step": step,
            "value": value,
        }

    def _execute_create_list(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        variable_name = node_config.get("variable_name") or node_config.get("name")
        if not isinstance(variable_name, str) or not variable_name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        items = _resolve_value(node_config.get("items", []), context)
        if not isinstance(items, list):
            return _failed_result(node, "data.list_items_invalid", "items must be a list")
        list_value = list(items)
        context.variables[variable_name.strip()] = list_value
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name.strip(),
            "items": list_value,
        }

    def _execute_list_append(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        variable_name = node_config.get("variable_name") or node_config.get("name")
        if not isinstance(variable_name, str) or not variable_name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        current = context.variables.get(variable_name.strip())
        if current is None:
            current = []
        if not isinstance(current, list):
            return _failed_result(node, "data.list_target_invalid", "target variable must be a list")
        value = _resolve_value(node_config.get("value"), context)
        updated = list(current)
        updated.append(value)
        context.variables[variable_name.strip()] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name.strip(),
            "value": value,
            "items": updated,
        }

    def _execute_list_extend(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        variable_name = node_config.get("variable_name") or node_config.get("name")
        if not isinstance(variable_name, str) or not variable_name.strip():
            return _failed_result(node, "data.variable_name_required", "variable name is required")
        current = context.variables.get(variable_name.strip())
        if current is None:
            current = []
        if not isinstance(current, list):
            return _failed_result(node, "data.list_target_invalid", "target variable must be a list")
        items = _resolve_value(node_config.get("items", []), context)
        if not isinstance(items, list):
            return _failed_result(node, "data.list_items_invalid", "items must be a list")
        updated = list(current)
        updated.extend(items)
        context.variables[variable_name.strip()] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name.strip(),
            "items": updated,
        }

    def _execute_list_get(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        index = _resolve_int(_resolve_value(node_config.get("index"), context), default=0)
        try:
            value = list_value[index]
        except IndexError:
            return _failed_result(node, "data.list_index_out_of_range", "list index is out of range")
        _store_optional_variable_name(node_config.get("output_variable_name"), context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "index": index,
            "value": value,
        }

    def _execute_list_set(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        index = _resolve_int(_resolve_value(node_config.get("index"), context), default=0)
        if index < 0 or index >= len(list_value):
            return _failed_result(node, "data.list_index_out_of_range", "list index is out of range")
        value = _resolve_value(node_config.get("value"), context)
        updated = list(list_value)
        updated[index] = value
        context.variables[variable_name] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "index": index,
            "value": value,
            "items": updated,
        }

    def _execute_list_index(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        value = _resolve_value(node_config.get("value"), context)
        try:
            index = list_value.index(value)
        except ValueError:
            return _failed_result(node, "data.list_value_not_found", "list value not found")
        _store_optional_variable_name(node_config.get("output_variable_name"), context, index)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "searched_value": value,
            "value": index,
        }

    def _execute_list_length(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        value = len(list_value)
        _store_optional_variable_name(node_config.get("output_variable_name"), context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "value": value,
        }

    def _execute_list_insert(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        index = _resolve_int(_resolve_value(node_config.get("index"), context), default=0)
        value = _resolve_value(node_config.get("value"), context)
        updated = list(list_value)
        if index < 0:
            index = 0
        if index > len(updated):
            index = len(updated)
        updated.insert(index, value)
        context.variables[variable_name] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "index": index,
            "value": value,
            "items": updated,
        }

    def _execute_list_remove(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        updated = list(list_value)
        if "index" in node_config:
            index = _resolve_int(_resolve_value(node_config.get("index"), context), default=0)
            if index < 0 or index >= len(updated):
                return _failed_result(node, "data.list_index_out_of_range", "list index is out of range")
            removed = updated.pop(index)
        else:
            value = _resolve_value(node_config.get("value"), context)
            try:
                updated.remove(value)
                removed = value
            except ValueError:
                return _failed_result(node, "data.list_value_not_found", "list value not found")
        context.variables[variable_name] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "value": removed,
            "items": updated,
        }

    def _execute_list_slice(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        start = _resolve_int(_resolve_value(node_config.get("start"), context), default=0)
        end_value = node_config.get("end")
        end = _resolve_int(_resolve_value(end_value, context), default=len(list_value)) if end_value is not None else len(list_value)
        sliced = list_value[start:end]
        _store_optional_variable_name(node_config.get("output_variable_name"), context, sliced)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "start": start,
            "end": end,
            "value": sliced,
        }

    def _execute_list_sort(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        updated = list(list_value)
        updated.sort()
        context.variables[variable_name] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "items": updated,
        }

    def _execute_list_reverse(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        list_value, variable_name = _require_runtime_list(node, context)
        if isinstance(list_value, dict):
            return list_value
        updated = list(list_value)
        updated.reverse()
        context.variables[variable_name] = updated
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name,
            "items": updated,
        }

    def _execute_evaluate_expression(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        expression = _resolve_value(node_config.get("expression"), context)
        if not isinstance(expression, str) or not expression.strip():
            return _failed_result(node, "data.expression_required", "expression is required")
        try:
            value = _safe_eval_expression(expression, context.variables)
        except ValueError as exc:
            return _failed_result(node, "data.expression_invalid", str(exc))
        _store_optional_variable(node_config, context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "expression": expression,
            "value": value,
        }

    def _execute_regex_replace(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        text = _resolve_value(node_config.get("text", ""), context)
        pattern = _resolve_value(node_config.get("pattern"), context)
        replacement = _resolve_value(node_config.get("replacement", ""), context)
        if not isinstance(text, str):
            return _failed_result(node, "data.regex_text_invalid", "text must be a string")
        if not isinstance(pattern, str) or not pattern:
            return _failed_result(node, "data.regex_pattern_required", "pattern is required")
        if not isinstance(replacement, str):
            replacement = str(replacement)
        try:
            value = re.sub(pattern, replacement, text)
        except re.error as exc:
            return _failed_result(node, "data.regex_pattern_invalid", str(exc))
        _store_optional_variable(node_config, context, value)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "value": value,
        }

    def _execute_write_text_file(self, node: dict, context: RuntimeContext) -> dict:
        if not self._is_file_access_allowed():
            return _failed_result(node, "file.access_denied", "file access is disabled")
        node_config = _node_config(node)
        path_value = _resolve_value(node_config.get("path"), context)
        if not isinstance(path_value, str) or not path_value.strip():
            return _failed_result(node, "file.path_required", "file path is required")
        encoding = str(_resolve_value(node_config.get("encoding", "utf-8"), context))
        content = _resolve_value(node_config.get("content", ""), context)
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        path = _resolve_runtime_path(path_value, context)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(path.resolve()),
            "encoding": encoding,
            "bytes_written": len(text.encode(encoding)),
        }

    def _execute_read_text_file(self, node: dict, context: RuntimeContext) -> dict:
        if not self._is_file_access_allowed():
            return _failed_result(node, "file.access_denied", "file access is disabled")
        node_config = _node_config(node)
        path_value = _resolve_value(node_config.get("path"), context)
        if not isinstance(path_value, str) or not path_value.strip():
            return _failed_result(node, "file.path_required", "file path is required")
        encoding = str(_resolve_value(node_config.get("encoding", "utf-8"), context))
        path = _resolve_runtime_path(path_value, context)
        content = path.read_text(encoding=encoding)
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(path.resolve()),
            "encoding": encoding,
            "content": content,
        }
        variable_name = node_config.get("variable_name")
        if isinstance(variable_name, str) and variable_name.strip():
            context.variables[variable_name.strip()] = content
        return result

    def _execute_read_csv_cell(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        table_result = _read_csv_table(node, context)
        if table_result.get("status") == "failed":
            return table_result
        row_index = _resolve_int(node_config.get("row_index"), default=0)
        column = _resolve_value(node_config.get("column"), context)
        rows = table_result["rows"]
        try:
            row = rows[row_index]
        except IndexError:
            return _failed_result(node, "file.csv_row_out_of_range", "CSV row_index is out of range")
        if isinstance(row, dict):
            if column is None:
                return _failed_result(node, "file.csv_column_required", "CSV column is required")
            value = row.get(str(column))
        else:
            column_index = _resolve_int(column, default=0)
            try:
                value = row[column_index]
            except IndexError:
                return _failed_result(node, "file.csv_column_out_of_range", "CSV column is out of range")
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": table_result["path"],
            "row_index": row_index,
            "column": column,
            "value": value,
        }
        _store_optional_variable(node_config, context, value)
        return result

    def _execute_read_csv_row(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        table_result = _read_csv_table(node, context)
        if table_result.get("status") == "failed":
            return table_result
        row_index = _resolve_int(node_config.get("row_index"), default=0)
        rows = table_result["rows"]
        try:
            row = rows[row_index]
        except IndexError:
            return _failed_result(node, "file.csv_row_out_of_range", "CSV row_index is out of range")
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": table_result["path"],
            "row_index": row_index,
            "row": row,
        }
        _store_optional_variable(node_config, context, row)
        return result

    def _execute_read_csv_table(self, node: dict, context: RuntimeContext) -> dict:
        table_result = _read_csv_table(node, context)
        if table_result.get("status") == "failed":
            return table_result
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": table_result["path"],
            "encoding": table_result["encoding"],
            "has_header": table_result["has_header"],
            "headers": table_result["headers"],
            "rows": table_result["rows"],
            "row_count": len(table_result["rows"]),
        }
        _store_optional_variable(_node_config(node), context, table_result["rows"])
        return result

    def _execute_write_excel_cell(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(node, context)
        if worksheet is None:
            return workbook_path
        cell = _resolve_value(node_config.get("cell"), context)
        if not isinstance(cell, str) or not cell.strip():
            workbook.close()
            return _failed_result(node, "excel.cell_required", "Excel cell is required")
        value = _resolve_value(node_config.get("value"), context)
        worksheet[cell.strip()] = value
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "cell": cell.strip(),
            "value": value,
        }

    def _execute_write_excel_row(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(node, context)
        if worksheet is None:
            return workbook_path
        row_index = _resolve_int(_resolve_value(node_config.get("row_index"), context), default=1)
        data = _resolve_value(node_config.get("data"), context)
        if row_index < 1:
            workbook.close()
            return _failed_result(node, "excel.row_out_of_range", "Excel row_index must be >= 1")
        values = _normalize_excel_row_payload(worksheet, data)
        for column_index, value in enumerate(values, start=1):
            worksheet.cell(row=row_index, column=column_index, value=value)
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "row_index": row_index,
            "row": values,
        }

    def _execute_write_excel_table(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(node, context)
        if worksheet is None:
            return workbook_path
        data = _resolve_value(node_config.get("data"), context)
        has_header = bool(_resolve_value(node_config.get("has_header", True), context))
        headers, rows = _normalize_excel_table_payload(data, has_header=has_header)
        _clear_worksheet(worksheet)
        current_row = 1
        if has_header and headers:
            for column_index, header in enumerate(headers, start=1):
                worksheet.cell(row=current_row, column=column_index, value=header)
            current_row += 1
        for row in rows:
            for column_index, value in enumerate(row, start=1):
                worksheet.cell(row=current_row, column=column_index, value=value)
            current_row += 1
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "has_header": has_header,
            "row_count": len(rows),
        }

    def _execute_write_excel_file(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        mode = str(_resolve_value(node_config.get("mode", "create"), context)).lower()
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(
            node,
            context,
            create_mode=(mode == "create"),
        )
        if worksheet is None:
            return workbook_path
        headers = _resolve_value(node_config.get("headers", []), context)
        rows = _resolve_value(node_config.get("rows", []), context)
        if not isinstance(headers, list):
            workbook.close()
            return _failed_result(node, "excel.headers_invalid", "Excel headers must be a list")
        if not isinstance(rows, list):
            workbook.close()
            return _failed_result(node, "excel.rows_invalid", "Excel rows must be a list")
        if mode == "create":
            _clear_worksheet(worksheet)
            current_row = 1
            if headers:
                for column_index, header in enumerate(headers, start=1):
                    worksheet.cell(row=current_row, column=column_index, value=header)
                current_row += 1
        else:
            current_row = worksheet.max_row + 1 if worksheet.max_row > 1 or worksheet["A1"].value is not None else 1
            if current_row == 1 and headers:
                for column_index, header in enumerate(headers, start=1):
                    worksheet.cell(row=current_row, column=column_index, value=header)
                current_row += 1
        for row in rows:
            row_values = list(row.values()) if isinstance(row, dict) else list(row)
            for column_index, value in enumerate(row_values, start=1):
                worksheet.cell(row=current_row, column=column_index, value=value)
            current_row += 1
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "mode": mode,
            "row_count": len(rows),
        }

    def _execute_update_excel_cells(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(node, context, create_if_not_exists=False)
        if worksheet is None:
            return workbook_path
        updates = _resolve_value(node_config.get("updates"), context)
        if not isinstance(updates, list):
            workbook.close()
            return _failed_result(node, "excel.updates_invalid", "Excel updates must be a list")
        updated_count = 0
        headers = [cell.value for cell in worksheet[1]]
        for update in updates:
            if not isinstance(update, dict):
                workbook.close()
                return _failed_result(node, "excel.update_invalid", "each Excel update must be an object")
            row_index = _resolve_int(update.get("row_index"), default=0)
            if row_index < 1:
                workbook.close()
                return _failed_result(node, "excel.row_out_of_range", "Excel row_index must be >= 1")
            if "column_name" in update:
                try:
                    column_index = headers.index(update.get("column_name")) + 1
                except ValueError:
                    workbook.close()
                    return _failed_result(node, "excel.column_not_found", "Excel column_name was not found")
            else:
                column_index = _resolve_int(update.get("column_index"), default=0)
                if column_index < 1:
                    workbook.close()
                    return _failed_result(node, "excel.column_out_of_range", "Excel column_index must be >= 1")
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=_resolve_value(update.get("value"), context),
            )
            updated_count += 1
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "updated_count": updated_count,
        }

    def _execute_update_excel_batch(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, workbook, worksheet = _load_excel_sheet_for_write(node, context, create_if_not_exists=False)
        if worksheet is None:
            return workbook_path
        condition = _resolve_value(node_config.get("condition"), context)
        updates = _resolve_value(node_config.get("updates"), context)
        if not isinstance(condition, str) or not condition.strip():
            workbook.close()
            return _failed_result(node, "excel.condition_required", "Excel update_batch requires condition")
        if not isinstance(updates, dict):
            workbook.close()
            return _failed_result(node, "excel.updates_invalid", "Excel update_batch updates must be an object")
        headers = [cell.value for cell in worksheet[1]]
        updated_count = 0
        for row_index in range(2, worksheet.max_row + 1):
            row_payload = {
                str(headers[column_index - 1]): worksheet.cell(row=row_index, column=column_index).value
                for column_index in range(1, len(headers) + 1)
            }
            try:
                matched = _evaluate_excel_batch_condition(condition, row_payload)
            except Exception as exc:
                workbook.close()
                return _failed_result(node, "excel.condition_invalid", str(exc))
            if not matched:
                continue
            for column_name, value in updates.items():
                try:
                    column_index = headers.index(column_name) + 1
                except ValueError:
                    workbook.close()
                    return _failed_result(node, "excel.column_not_found", "Excel column_name was not found")
                worksheet.cell(row=row_index, column=column_index, value=_resolve_value(value, context))
            updated_count += 1
        workbook.save(workbook_path)
        workbook.close()
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": str(workbook_path.resolve()),
            "sheet_name": worksheet.title,
            "updated_count": updated_count,
        }

    def _execute_read_excel_cell(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, worksheet = _require_excel_sheet(node, context)
        if worksheet is None:
            return workbook_path
        cell = _resolve_value(node_config.get("cell"), context)
        if not isinstance(cell, str) or not cell.strip():
            worksheet.parent.close()
            return _failed_result(node, "excel.cell_required", "Excel cell is required")
        value = worksheet[cell.strip()].value
        resolved_path = str(workbook_path.resolve())
        sheet_name = worksheet.title
        worksheet.parent.close()
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": resolved_path,
            "sheet_name": sheet_name,
            "cell": cell.strip(),
            "value": value,
        }
        _store_optional_variable(node_config, context, value)
        return result

    def _execute_read_excel_row(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        workbook_path, worksheet = _require_excel_sheet(node, context)
        if worksheet is None:
            return workbook_path
        row_index = _resolve_int(_resolve_value(node_config.get("row_index"), context), default=1)
        if row_index < 1:
            worksheet.parent.close()
            return _failed_result(node, "excel.row_out_of_range", "Excel row_index must be >= 1")
        try:
            row = [cell.value for cell in worksheet[row_index]]
        except (IndexError, ValueError):
            worksheet.parent.close()
            return _failed_result(node, "excel.row_out_of_range", "Excel row_index is out of range")
        resolved_path = str(workbook_path.resolve())
        sheet_name = worksheet.title
        worksheet.parent.close()
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": resolved_path,
            "sheet_name": sheet_name,
            "row_index": row_index,
            "row": row,
        }
        _store_optional_variable(node_config, context, row)
        return result

    def _execute_read_excel_table(self, node: dict, context: RuntimeContext) -> dict:
        table_result = _read_excel_table(node, context)
        if table_result.get("status") == "failed":
            return table_result
        result = {
            "status": "succeeded",
            "node_id": node["node_id"],
            "path": table_result["path"],
            "sheet_name": table_result["sheet_name"],
            "has_header": table_result["has_header"],
            "headers": table_result["headers"],
            "rows": table_result["rows"],
            "row_count": len(table_result["rows"]),
        }
        _store_optional_variable(_node_config(node), context, table_result["rows"])
        return result

    def _execute_python_run(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        if not self._is_python_execution_allowed():
            return _failed_result(node, "python.execution_disabled", "python execution is disabled")
        code = _resolve_value(node_config.get("code"), context)
        if not isinstance(code, str) or not code.strip():
            return _failed_result(node, "python.code_required", "python.run requires node_config.code")
        default_variable_name = node_config.get("variable_name")
        scope = {
            "variables": context.variables,
            "page": context.browser_runtime.get("page"),
            "browser": context.browser_runtime.get("browser"),
            "result": None,
            "result_variable": default_variable_name,
        }
        capture_stdout_stderr = self._should_capture_stdout_stderr()
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        try:
            compiled = compile(code, "<weconduct-python.run>", "exec")
            stdout_target = stdout_buffer if capture_stdout_stderr else io.StringIO()
            stderr_target = stderr_buffer if capture_stdout_stderr else io.StringIO()
            with redirect_stdout(stdout_target), redirect_stderr(stderr_target):
                exec(compiled, {"__builtins__": _PYTHON_SAFE_BUILTINS}, scope)
        except PythonImportNotAllowed as exc:
            return {
                "status": "failed",
                "node_id": node["node_id"],
                "error_code": "python.import_not_allowed",
                "message": str(exc),
                "exception_type": type(exc).__name__,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "node_id": node["node_id"],
                "error_code": "python.execution_failed",
                "message": str(exc),
                "exception_type": type(exc).__name__,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
            }
        result = scope.get("result")
        result_variable = scope.get("result_variable")
        if isinstance(result_variable, str) and result_variable.strip():
            context.variables[result_variable.strip()] = result
            result_variable = result_variable.strip()
        else:
            result_variable = None
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "result": result,
            "result_variable": result_variable,
            "stdout": stdout_buffer.getvalue() if capture_stdout_stderr else "",
            "stderr": stderr_buffer.getvalue() if capture_stdout_stderr else "",
        }

    def _is_file_access_allowed(self) -> bool:
        return bool(self._runtime_settings.get("allow_file_access", True))

    def _is_python_execution_allowed(self) -> bool:
        return bool(self._runtime_settings.get("allow_external_programs", False))

    def _is_browser_executor_allowed(self) -> bool:
        return bool(self._runtime_settings.get("allow_browser_executor", False))

    def _is_local_network_access_allowed(self) -> bool:
        return bool(self._runtime_settings.get("allow_local_network_access", False))

    def _should_capture_stdout_stderr(self) -> bool:
        return bool(self._runtime_settings.get("capture_stdout_stderr", True))

    def _execute_session_apply_auth_session(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        page = _require_browser_page(context)
        cookies = _resolve_value(node_config.get("cookies", []), context)
        if cookies is None:
            cookies = []
        if not isinstance(cookies, list):
            return _failed_result(node, "session.cookies_invalid", "cookies must be a list")
        normalized_cookies = []
        for cookie in cookies:
            if not isinstance(cookie, dict):
                return _failed_result(node, "session.cookie_invalid", "each cookie must be an object")
            name = cookie.get("name")
            value = cookie.get("value")
            if not isinstance(name, str) or not name.strip():
                return _failed_result(node, "session.cookie_name_required", "cookie name is required")
            normalized = dict(cookie)
            normalized["name"] = name.strip()
            normalized["value"] = "" if value is None else str(value)
            normalized_cookies.append(normalized)
        if normalized_cookies:
            page.context.add_cookies(normalized_cookies)

        local_storage = _resolve_value(node_config.get("local_storage", {}), context)
        storage_origin_count = _apply_local_storage(page, local_storage)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "cookie_count": len(normalized_cookies),
            "local_storage_origin_count": storage_origin_count,
        }

    def _execute_dialog_set_agent_config(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        config = context.browser_runtime.setdefault("dialog_config", {})
        default_action = _resolve_value(node_config.get("default_action", node_config.get("action", "accept")), context)
        prompt_text = _resolve_value(node_config.get("prompt_text", ""), context)
        if not isinstance(default_action, str) or default_action.strip() not in {"accept", "dismiss"}:
            return _failed_result(node, "dialog.action_invalid", "default_action must be accept or dismiss")
        config["default_action"] = default_action.strip()
        config["prompt_text"] = "" if prompt_text is None else str(prompt_text)
        _ensure_dialog_handler(context)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "default_action": config["default_action"],
            "prompt_text": config["prompt_text"],
        }

    def _execute_dialog_switch_dialog_mode(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        mode = _resolve_value(node_config.get("mode", "auto"), context)
        if not isinstance(mode, str) or not mode.strip():
            return _failed_result(node, "dialog.mode_required", "dialog mode is required")
        normalized_mode = mode.strip()
        if normalized_mode not in {"auto", "manual", "accept", "dismiss"}:
            return _failed_result(node, "dialog.mode_invalid", "dialog mode must be auto, manual, accept, or dismiss")
        config = context.browser_runtime.setdefault("dialog_config", {})
        config["mode"] = normalized_mode
        if normalized_mode in {"accept", "dismiss"}:
            config["default_action"] = normalized_mode
        _ensure_dialog_handler(context)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "mode": normalized_mode,
            "default_action": config.get("default_action", "accept"),
        }

    def _execute_dialog_watch_dialogs(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        _ensure_dialog_handler(context)
        timeout_ms = _resolve_int(_resolve_value(node_config.get("timeout"), context), default=0)
        if timeout_ms > 0:
            _require_browser_page(context).wait_for_timeout(timeout_ms)
        records = list(context.browser_runtime.get("dialog_records", []))
        _store_optional_variable(node_config, context, records)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "dialog_count": len(records),
            "dialogs": records,
        }

    def _execute_dialog_handle_dialogs(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        _ensure_dialog_handler(context)
        records = list(context.browser_runtime.get("dialog_records", []))
        if bool(_resolve_value(node_config.get("clear_after", False), context)):
            context.browser_runtime["dialog_records"] = []
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "handled_count": len(records),
            "dialogs": records,
            "cleared": bool(node_config.get("clear_after", False)),
        }

    def _execute_control_foreach(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        variable_name = node_config.get("variable") or node_config.get("variable_name")
        if not isinstance(variable_name, str) or not variable_name.strip():
            return _failed_result(node, "control.variable_required", "variable is required")
        items = context.variables.get(variable_name.strip())
        if not isinstance(items, list):
            return _failed_result(node, "control.foreach_items_invalid", "variable must be a list")
        item_var = node_config.get("item_var")
        if not isinstance(item_var, str) or not item_var.strip():
            item_var = "item"
        index_var = node_config.get("index_var")
        if not isinstance(index_var, str) or not index_var.strip():
            index_var = "index"
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "variable_name": variable_name.strip(),
            "item_var": item_var.strip(),
            "index_var": index_var.strip(),
            "items": list(items),
            "iteration_count": len(items),
        }

    def _execute_control_jump_to_step(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        target_node_id = node_config.get("target_node_id")
        target_step = node_config.get("target_step")
        condition = _resolve_value(node_config.get("condition", "true"), context)
        max_jumps = _resolve_int(_resolve_value(node_config.get("max_jumps", -1), context), default=-1)
        if not isinstance(condition, str):
            condition = str(condition)
        should_jump = _evaluate_jump_condition(condition, context.variables)
        if not should_jump:
            return {
                "status": "succeeded",
                "node_id": node["node_id"],
                "jump_executed": False,
                "jump_count": 0,
                "target_node_id": target_node_id,
                "target_step": target_step,
            }
        flow_runtime = context.flow_runtime.setdefault("jump_runtime", {})
        jump_key = node["node_id"]
        jump_count = int(flow_runtime.get(jump_key, 0))
        if max_jumps >= 0 and jump_count >= max_jumps:
            return {
                "status": "succeeded",
                "node_id": node["node_id"],
                "jump_executed": False,
                "jump_count": jump_count,
                "stopped_by_max_jumps": True,
                "target_node_id": target_node_id,
                "target_step": target_step,
            }
        flow_runtime[jump_key] = jump_count + 1
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "jump_executed": True,
            "jump_count": jump_count + 1,
            "stopped_by_max_jumps": False,
            "target_node_id": target_node_id,
            "target_step": target_step,
        }

    def _execute_control_end_foreach(self, node: dict, context: RuntimeContext) -> dict:
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "end_marker": True,
        }

    def _execute_control_foreach_continue(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        condition = _resolve_value(node_config.get("condition", "true"), context)
        if not isinstance(condition, str):
            condition = str(condition)
        level = _resolve_int(_resolve_value(node_config.get("level", 1), context), default=1)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "continue_triggered": _evaluate_jump_condition(condition, context.variables),
            "level": level if level >= 1 else 1,
        }

    def _execute_control_foreach_break(self, node: dict, context: RuntimeContext) -> dict:
        node_config = _node_config(node)
        condition = _resolve_value(node_config.get("condition", "true"), context)
        if not isinstance(condition, str):
            condition = str(condition)
        level = _resolve_int(_resolve_value(node_config.get("level", 1), context), default=1)
        return {
            "status": "succeeded",
            "node_id": node["node_id"],
            "break_triggered": _evaluate_jump_condition(condition, context.variables),
            "level": level if level >= 1 else 1,
        }

    def execute_component_graph(
        self,
        *,
        graph_model: dict,
        inputs: dict[str, Any] | None = None,
    ) -> dict:
        graph_nodes = graph_model.get("nodes") if isinstance(graph_model, dict) else None
        graph_edges = graph_model.get("edges") if isinstance(graph_model, dict) else None
        if not isinstance(graph_nodes, list) or not isinstance(graph_edges, list):
            return {
                "status": "failed",
                "error_code": "component.graph_invalid",
                "message": "component graph is invalid",
            }
        context = RuntimeContext()
        context.variables.update(inputs or {})
        node_lookup = {node.get("node_id"): node for node in graph_nodes if isinstance(node, dict)}
        if len(node_lookup) != len(graph_nodes):
            return {
                "status": "failed",
                "error_code": "component.graph_invalid",
                "message": "component graph node ids are invalid",
            }
        control_edges_by_source = _build_control_edges_by_source(graph_edges)
        node_outputs: dict[str, Any] = {}
        executed_node_ids: list[str] = []
        index = 0
        max_steps = max(1, len(graph_nodes) * 20)
        step_count = 0
        try:
            while 0 <= index < len(graph_nodes):
                if step_count >= max_steps:
                    return {
                        "status": "failed",
                        "error_code": "component.execution_step_limit_exceeded",
                        "message": "component execution step limit exceeded",
                        "executed_node_ids": executed_node_ids,
                        "outputs": dict(node_outputs),
                        "variables": dict(context.variables),
                    }
                step_count += 1
                node = graph_nodes[index]
                if not isinstance(node, dict):
                    return {
                        "status": "failed",
                        "error_code": "component.graph_invalid",
                        "message": "component node is invalid",
                    }
                output = execute_runtime_node(node, context, self)
                node_outputs[node["node_id"]] = output
                executed_node_ids.append(node["node_id"])
                if isinstance(output, dict) and output.get("status") == "failed":
                    return {
                        "status": "failed",
                        "error_code": output.get("error_code") or "runtime.node_failed",
                        "message": output.get("message", "runtime node failed"),
                        "executed_node_ids": executed_node_ids,
                        "outputs": dict(node_outputs),
                        "variables": dict(context.variables),
                    }
                next_index = index + 1
                if node.get("node_kind") == "control.foreach":
                    loop_body_end, loop_exit = _resolve_foreach_targets(node["node_id"], control_edges_by_source, node_lookup)
                    iterable = output.get("items", []) if isinstance(output, dict) else []
                    if not isinstance(iterable, list):
                        return {
                            "status": "failed",
                            "error_code": "control.foreach_items_invalid",
                            "message": "foreach items must be a list",
                            "executed_node_ids": executed_node_ids,
                            "outputs": dict(node_outputs),
                            "variables": dict(context.variables),
                        }
                    if not iterable:
                        if loop_exit is not None:
                            index = loop_exit
                            continue
                        next_index = index + 1
                    else:
                        item_var = output.get("item_var", "item")
                        index_var = output.get("index_var", "index")
                        body_start = _find_node_index(graph_nodes, loop_body_end) if loop_body_end is not None else None
                        exit_index = _find_node_index(graph_nodes, loop_exit) if loop_exit is not None else None
                        if body_start is None:
                            return {
                                "status": "failed",
                                "error_code": "control.foreach_body_missing",
                                "message": "foreach body node is missing",
                                "executed_node_ids": executed_node_ids,
                                "outputs": dict(node_outputs),
                                "variables": dict(context.variables),
                            }
                        for item_index, item_value in enumerate(iterable):
                            context.variables[item_var] = item_value
                            context.variables[index_var] = item_index
                            body_cursor = body_start
                            while True:
                                if step_count >= max_steps:
                                    return {
                                        "status": "failed",
                                        "error_code": "component.execution_step_limit_exceeded",
                                        "message": "component execution step limit exceeded",
                                        "executed_node_ids": executed_node_ids,
                                        "outputs": dict(node_outputs),
                                        "variables": dict(context.variables),
                                    }
                                step_count += 1
                                body_node = graph_nodes[body_cursor]
                                body_output = execute_runtime_node(body_node, context, self)
                                node_outputs[body_node["node_id"]] = body_output
                                executed_node_ids.append(body_node["node_id"])
                                if isinstance(body_output, dict) and body_output.get("status") == "failed":
                                    return {
                                        "status": "failed",
                                        "error_code": body_output.get("error_code") or "runtime.node_failed",
                                        "message": body_output.get("message", "runtime node failed"),
                                        "executed_node_ids": executed_node_ids,
                                        "outputs": dict(node_outputs),
                                        "variables": dict(context.variables),
                                    }
                                if body_node["node_id"] == loop_body_end:
                                    break
                                body_cursor += 1
                            if exit_index is not None:
                                context.flow_runtime["foreach_exit_index"] = exit_index
                        if loop_exit is not None:
                            index = loop_exit
                            continue
                        next_index = index + 1
                elif node.get("node_kind") == "control.jump_to_step":
                    jump_result = output
                    if isinstance(jump_result, dict) and jump_result.get("jump_executed") is True:
                        target_node_id = jump_result.get("target_node_id")
                        target_index = None
                        if isinstance(target_node_id, str) and target_node_id in node_lookup:
                            target_index = _find_node_index(graph_nodes, target_node_id)
                        elif jump_result.get("target_step") is not None:
                            target_index = _resolve_step_target_index(graph_nodes, jump_result.get("target_step"))
                        if target_index is None:
                            return {
                                "status": "failed",
                                "error_code": "control.jump_target_missing",
                                "message": "jump target node was not found",
                                "executed_node_ids": executed_node_ids,
                                "outputs": dict(node_outputs),
                                "variables": dict(context.variables),
                            }
                        next_index = target_index
                        continue
                index = next_index
            return {
                "status": "succeeded",
                "executed_node_ids": executed_node_ids,
                "outputs": node_outputs,
                "variables": dict(context.variables),
            }
        finally:
            context.close()


def execute_runtime_node(node: dict, context: RuntimeContext, registry: RuntimeExecutorRegistry) -> dict:
    output = registry.execute(node.get("node_kind"), node, context)
    context.node_outputs[node["node_id"]] = output
    return output


def _node_config(node: dict) -> dict:
    node_config = node.get("node_config")
    base_config = dict(node_config) if isinstance(node_config, dict) else {}
    runtime_input_overrides = node.get("__runtime_input_overrides__")
    if not isinstance(runtime_input_overrides, dict) or not runtime_input_overrides:
        return base_config
    merged_config = dict(base_config)
    for raw_key, value in runtime_input_overrides.items():
        if not isinstance(raw_key, str):
            continue
        normalized_key = raw_key.strip()
        if not normalized_key:
            continue
        if "." not in normalized_key:
            merged_config[normalized_key] = value
            continue
        segments = [segment.strip() for segment in normalized_key.split(".") if segment.strip()]
        if not segments:
            continue
        cursor = merged_config
        for segment in segments[:-1]:
            current_value = cursor.get(segment)
            if not isinstance(current_value, dict):
                current_value = {}
                cursor[segment] = current_value
            cursor = current_value
        cursor[segments[-1]] = value
    return merged_config


def _failed_result(node: dict, error_code: str, message: str) -> dict:
    return {
        "status": "failed",
        "node_id": node["node_id"],
        "error_code": error_code,
        "message": message,
    }


def _last_node_output(context: RuntimeContext) -> Any:
    upstream = None
    for output in context.node_outputs.values():
        upstream = output
    return upstream


def _build_control_edges_by_source(edges: list[Any]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if edge.get("relation_layer") != "control":
            continue
        source_id = edge.get("from_node_id")
        if not isinstance(source_id, str):
            continue
        result.setdefault(source_id, []).append(edge)
    return result


def _resolve_foreach_targets(
    source_node_id: str,
    control_edges_by_source: dict[str, list[dict]],
    node_lookup: dict[str, dict],
) -> tuple[str | None, str | None]:
    edges = control_edges_by_source.get(source_node_id, [])
    if not edges:
        return None, None
    ordered_targets = [
        edge.get("to_node_id")
        for edge in edges
        if isinstance(edge.get("to_node_id"), str) and edge.get("to_node_id") in node_lookup
    ]
    if not ordered_targets:
        return None, None
    loop_body = ordered_targets[0]
    loop_exit = ordered_targets[1] if len(ordered_targets) > 1 else None
    return loop_body, loop_exit


def _find_node_index(graph_nodes: list[dict], node_id: str) -> int | None:
    for index, node in enumerate(graph_nodes):
        if isinstance(node, dict) and node.get("node_id") == node_id:
            return index
    return None


def _resolve_step_target_index(graph_nodes: list[dict], target_step: Any) -> int | None:
    if isinstance(target_step, int):
        index = target_step - 1
        return index if 0 <= index < len(graph_nodes) else None
    if isinstance(target_step, str) and target_step.strip().isdigit():
        index = int(target_step.strip()) - 1
        return index if 0 <= index < len(graph_nodes) else None
    return None


def _evaluate_jump_condition(condition: str, variables: dict[str, Any]) -> bool:
    normalized = condition.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", ""}:
        return False
    try:
        value = _safe_eval_expression(condition, variables)
        return bool(value)
    except Exception:
        return False


def _decode_http_body(raw_body: bytes, headers: dict) -> Any:
    body_text = raw_body.decode("utf-8", errors="replace")
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
    if "application/json" in content_type.lower():
        try:
            return json.loads(body_text)
        except json.JSONDecodeError:
            return body_text
    return body_text


_VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")

_WEB_TABLE_EXTRACT_SCRIPT = """
(table) => {
  const rows = Array.from(table.querySelectorAll('tr'));
  const headerCells = Array.from(table.querySelectorAll('thead tr:first-child th, thead tr:first-child td'));
  const headers = headerCells.map((cell) => cell.textContent.trim());
  const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
  const sourceRows = bodyRows.length > 0 ? bodyRows : rows.slice(headers.length > 0 ? 1 : 0);
  const extractedRows = sourceRows.map((row) => {
    const values = Array.from(row.querySelectorAll('th, td')).map((cell) => cell.textContent.trim());
    if (headers.length > 0) {
      const item = {};
      headers.forEach((header, index) => {
        item[header || String(index)] = values[index] || '';
      });
      return item;
    }
    return values;
  });
  return { headers, rows: extractedRows };
}
"""

_PYTHON_ALLOWED_IMPORTS = {
    "csv",
    "datetime",
    "json",
    "math",
    "re",
    "statistics",
}


class PythonImportNotAllowed(ImportError):
    pass


def _python_safe_import(
    name: str,
    globals: dict | None = None,  # noqa: A002
    locals: dict | None = None,  # noqa: A002
    fromlist: tuple | list = (),
    level: int = 0,
) -> Any:
    root_name = name.split(".", 1)[0]
    if level != 0 or root_name not in _PYTHON_ALLOWED_IMPORTS:
        raise PythonImportNotAllowed(f"python.run import is not allowed: {name}")
    return __import__(name, globals, locals, fromlist, level)


_PYTHON_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "__import__": _python_safe_import,
}


def _resolve_value(value: Any, context: RuntimeContext) -> Any:
    if isinstance(value, str):
        return _resolve_string(value, context)
    if isinstance(value, list):
        return [_resolve_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, context) for key, item in value.items()}
    return value


def _resolve_string(value: str, context: RuntimeContext) -> Any:
    matches = list(_VARIABLE_PATTERN.finditer(value))
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return _lookup_runtime_reference(matches[0].group(1), context)

    def replace_match(match: re.Match) -> str:
        resolved = _lookup_runtime_reference(match.group(1), context)
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved, ensure_ascii=False)
        return "" if resolved is None else str(resolved)

    return _VARIABLE_PATTERN.sub(replace_match, value)


def _lookup_runtime_reference(reference: str, context: RuntimeContext) -> Any:
    if reference.startswith("node."):
        parts = reference.split(".")
        if len(parts) < 3:
            return None
        node_id = parts[1]
        current: Any = context.node_outputs.get(node_id)
        for part in parts[2:]:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
    return context.variables.get(reference)


def _read_csv_table(node: dict, context: RuntimeContext) -> dict:
    node_config = _node_config(node)
    path_value = _resolve_value(node_config.get("path"), context)
    if not isinstance(path_value, str) or not path_value.strip():
        return _failed_result(node, "file.path_required", "file path is required")
    encoding = str(_resolve_value(node_config.get("encoding", "utf-8"), context))
    has_header = bool(_resolve_value(node_config.get("has_header", True), context))
    path = _resolve_runtime_path(path_value, context)
    with path.open("r", encoding=encoding, newline="") as csv_file:
        if has_header:
            reader = csv.DictReader(csv_file)
            rows = [dict(row) for row in reader]
            headers = list(reader.fieldnames or [])
        else:
            reader = csv.reader(csv_file)
            rows = [list(row) for row in reader]
            headers = []
    return {
        "status": "succeeded",
        "node_id": node["node_id"],
        "path": str(path.resolve()),
        "encoding": encoding,
        "has_header": has_header,
        "headers": headers,
        "rows": rows,
    }


def _require_excel_sheet(node: dict, context: RuntimeContext) -> tuple[Path | dict, Any | None]:
    node_config = _node_config(node)
    path_value = _resolve_value(node_config.get("path"), context)
    if not isinstance(path_value, str) or not path_value.strip():
        return _failed_result(node, "excel.path_required", "Excel file path is required"), None
    sheet_name = _resolve_value(node_config.get("sheet_name"), context)
    if not isinstance(sheet_name, str) or not sheet_name.strip():
        return _failed_result(node, "excel.sheet_name_required", "Excel sheet_name is required"), None
    path = _resolve_runtime_path(path_value, context)
    if not path.exists():
        return _failed_result(node, "excel.path_missing", "Excel file path does not exist"), None
    try:
        workbook = load_workbook(path)
    except (BadZipFile, InvalidFileException, OSError) as exc:
        return _failed_result(node, "excel.workbook_invalid", str(exc)), None
    if sheet_name.strip() not in workbook.sheetnames:
        workbook.close()
        return _failed_result(node, "excel.sheet_missing", "Excel sheet_name does not exist"), None
    worksheet = workbook[sheet_name.strip()]
    return path, worksheet


def _load_excel_sheet_for_write(
    node: dict,
    context: RuntimeContext,
    *,
    create_if_not_exists: bool = True,
    create_mode: bool = False,
) -> tuple[Path | dict, Workbook | None, Any | None]:
    node_config = _node_config(node)
    path_value = _resolve_value(node_config.get("path"), context)
    if not isinstance(path_value, str) or not path_value.strip():
        return _failed_result(node, "excel.path_required", "Excel file path is required"), None, None
    sheet_name = _resolve_value(node_config.get("sheet_name", "Sheet1"), context)
    if not isinstance(sheet_name, str) or not sheet_name.strip():
        return _failed_result(node, "excel.sheet_name_required", "Excel sheet_name is required"), None, None
    path = _resolve_runtime_path(path_value, context)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not create_mode:
        try:
            workbook = load_workbook(path)
        except (BadZipFile, InvalidFileException, OSError) as exc:
            return _failed_result(node, "excel.workbook_invalid", str(exc)), None, None
    elif create_if_not_exists or create_mode:
        workbook = Workbook()
        workbook.active.title = sheet_name.strip()
    else:
        return _failed_result(node, "excel.path_missing", "Excel file path does not exist"), None, None
    worksheet = workbook[sheet_name.strip()] if sheet_name.strip() in workbook.sheetnames else workbook.create_sheet(sheet_name.strip())
    return path, workbook, worksheet


def _read_excel_table(node: dict, context: RuntimeContext) -> dict:
    node_config = _node_config(node)
    workbook_path, worksheet = _require_excel_sheet(node, context)
    if worksheet is None:
        return workbook_path
    has_header = bool(_resolve_value(node_config.get("has_header", False), context))
    rows_raw = list(worksheet.iter_rows(values_only=True))
    headers: list[Any] = []
    rows: list[Any]
    if has_header and rows_raw:
        headers = list(rows_raw[0])
        rows = [
            {str(headers[index]): value for index, value in enumerate(row)}
            for row in rows_raw[1:]
        ]
    else:
        rows = [list(row) for row in rows_raw]
    result = {
        "status": "succeeded",
        "node_id": node["node_id"],
        "path": str(workbook_path.resolve()),
        "sheet_name": worksheet.title,
        "has_header": has_header,
        "headers": headers,
        "rows": rows,
    }
    worksheet.parent.close()
    return result


def _clear_worksheet(worksheet: Any) -> None:
    if worksheet.max_row >= 1:
        worksheet.delete_rows(1, worksheet.max_row)


def _normalize_excel_row_payload(worksheet: Any, data: Any) -> list[Any]:
    if isinstance(data, dict):
        headers = [cell.value for cell in worksheet[1] if cell.value is not None]
        if headers:
            return [data.get(str(header)) for header in headers]
        return list(data.values())
    if isinstance(data, list):
        return list(data)
    raise ValueError("excel row data must be a list or object")


def _normalize_excel_table_payload(data: Any, *, has_header: bool) -> tuple[list[Any], list[list[Any]]]:
    if not isinstance(data, list):
        raise ValueError("excel table data must be a list")
    if not data:
        return [], []
    first = data[0]
    if isinstance(first, dict):
        headers = list(first.keys())
        rows = [[item.get(header) for header in headers] for item in data]
        return (headers if has_header else []), rows
    return [], [list(item) for item in data]


def _evaluate_excel_batch_condition(condition: str, row: dict[str, Any]) -> bool:
    result = eval(condition, {"__builtins__": {}}, {"row": row})
    return bool(result)


def _resolve_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _store_optional_variable(node_config: dict, context: RuntimeContext, value: Any) -> None:
    variable_name = node_config.get("variable_name")
    if isinstance(variable_name, str) and variable_name.strip():
        context.variables[variable_name.strip()] = value


def _store_optional_variable_name(variable_name: Any, context: RuntimeContext, value: Any) -> None:
    if isinstance(variable_name, str) and variable_name.strip():
        context.variables[variable_name.strip()] = value


def _resolve_runtime_path(path_value: str, context: RuntimeContext) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    base_directory = context.project_directory or context.workspace_root
    if base_directory is None:
        return path.resolve()
    return (base_directory / path).resolve()


def _require_selector(node: dict, context: RuntimeContext) -> str | dict:
    selector = _resolve_value(_node_config(node).get("selector"), context)
    if not isinstance(selector, str) or not selector.strip():
        return _failed_result(node, "browser.selector_required", "selector is required")
    return selector.strip()


def _require_runtime_list(node: dict, context: RuntimeContext) -> tuple[list[Any] | dict, str]:
    node_config = _node_config(node)
    variable_name = node_config.get("variable_name") or node_config.get("name")
    if not isinstance(variable_name, str) or not variable_name.strip():
        return _failed_result(node, "data.variable_name_required", "variable name is required"), ""
    current = context.variables.get(variable_name.strip())
    if not isinstance(current, list):
        return (
            _failed_result(node, "data.list_target_invalid", "target variable must be a list"),
            variable_name.strip(),
        )
    return list(current), variable_name.strip()


def _require_browser_page(context: RuntimeContext) -> Page:
    page = context.browser_runtime.get("page")
    if page is not None:
        return page
    launch_options = context.browser_runtime.get("launch_options")
    if not isinstance(launch_options, dict):
        launch_options = {}
    chromium_launch_kwargs: dict[str, Any] = {
        "headless": bool(launch_options.get("headless", True))
    }
    if "slow_mo_ms" in launch_options:
        chromium_launch_kwargs["slow_mo"] = _resolve_int(launch_options.get("slow_mo_ms"), default=0)
    playwright: Playwright = sync_playwright().start()
    chromium_launch_kwargs["channel"] = "msedge"
    browser: Browser = playwright.chromium.launch(**chromium_launch_kwargs)
    page = browser.new_page()
    context.browser_runtime["playwright"] = playwright
    context.browser_runtime["browser"] = browser
    context.browser_runtime["page"] = page
    return page


def _resolve_browser_launch_config(value: Any, context: RuntimeContext) -> dict[str, Any]:
    resolved = _resolve_value(value, context)
    if not isinstance(resolved, dict):
        return {}
    browser_config: dict[str, Any] = {}
    if "headless" in resolved:
        browser_config["headless"] = bool(resolved.get("headless"))
    if "slow_mo_ms" in resolved:
        browser_config["slow_mo_ms"] = _resolve_int(resolved.get("slow_mo_ms"), default=0)
    return browser_config


def _apply_local_storage(page: Page, local_storage: Any) -> int:
    if local_storage in (None, {}, []):
        return 0
    origin_items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(local_storage, dict):
        for origin, items in local_storage.items():
            if isinstance(origin, str) and origin.strip() and isinstance(items, dict):
                origin_items.append((origin.strip(), items))
    elif isinstance(local_storage, list):
        for item in local_storage:
            if not isinstance(item, dict):
                continue
            origin = item.get("origin")
            items = item.get("items")
            if isinstance(origin, str) and origin.strip() and isinstance(items, dict):
                origin_items.append((origin.strip(), items))
    else:
        raise ValueError("local_storage must be an object or list")

    applied_count = 0
    current_origin = _page_origin(page.url)
    for origin, items in origin_items:
        target_page = page
        opened_temp_page = None
        if current_origin != origin:
            opened_temp_page = page.context.new_page()
            target_page = opened_temp_page
            target_page.goto(origin, wait_until="domcontentloaded")
        target_page.evaluate(
            """
            (items) => {
              for (const [key, value] of Object.entries(items)) {
                window.localStorage.setItem(key, String(value));
              }
            }
            """,
            items,
        )
        if opened_temp_page is not None:
            opened_temp_page.close()
        applied_count += 1
    return applied_count


def _page_origin(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _ensure_dialog_handler(context: RuntimeContext) -> None:
    page = _require_browser_page(context)
    if context.browser_runtime.get("dialog_handler_installed") is True:
        return
    context.browser_runtime.setdefault("dialog_records", [])
    context.browser_runtime.setdefault(
        "dialog_config",
        {
            "mode": "auto",
            "default_action": "accept",
            "prompt_text": "",
        },
    )

    def handle_dialog(dialog: Any) -> None:
        config = context.browser_runtime.setdefault("dialog_config", {})
        mode = str(config.get("mode", "auto"))
        action = str(config.get("default_action", "accept"))
        if mode in {"accept", "dismiss"}:
            action = mode
        record = {
            "type": dialog.type,
            "message": dialog.message,
            "default_value": dialog.default_value,
            "action": action,
        }
        try:
            if action == "dismiss":
                dialog.dismiss()
            else:
                dialog.accept(str(config.get("prompt_text", "")))
        except Exception as exc:
            record["error"] = str(exc)
        context.browser_runtime.setdefault("dialog_records", []).append(record)

    page.on("dialog", handle_dialog)
    context.browser_runtime["dialog_handler_installed"] = True


def _require_browser_target(context: RuntimeContext) -> Page | Frame:
    current_frame = context.browser_runtime.get("current_frame")
    if isinstance(current_frame, Frame):
        if current_frame.is_detached():
            context.browser_runtime.pop("current_frame", None)
            context.browser_runtime["frame_depth"] = 0
            return _require_browser_page(context)
        return current_frame
    return _require_browser_page(context)


def _reset_browser_frame_context(context: RuntimeContext) -> None:
    context.browser_runtime.pop("current_frame", None)
    context.browser_runtime["frame_stack"] = []


def _resolve_browser_frame(node_config: dict, context: RuntimeContext) -> Frame | None:
    page = _require_browser_page(context)
    selector = _resolve_value(node_config.get("selector"), context)
    name = _resolve_value(node_config.get("name"), context)
    url_contains = _resolve_value(node_config.get("url_contains"), context)
    index = _resolve_int(_resolve_value(node_config.get("index"), context), default=-1)
    if isinstance(selector, str) and selector.strip():
        frame_handle = page.locator(selector.strip()).element_handle()
        return frame_handle.content_frame() if frame_handle is not None else None
    for frame in page.frames:
        if isinstance(name, str) and name.strip() and frame.name == name.strip():
            return frame
        if isinstance(url_contains, str) and url_contains.strip() and url_contains.strip() in frame.url:
            return frame
    if index >= 0:
        frames = page.frames
        return frames[index] if index < len(frames) else None
    return None


def _wait_for_browser_url(target: Page | Frame, url_pattern: str, timeout_ms: int) -> str | None:
    started_at = monotonic()
    page = target.page if isinstance(target, Frame) else target
    while (monotonic() - started_at) * 1000 <= timeout_ms:
        current_url = target.url
        if url_pattern in current_url:
            return current_url
        page.wait_for_timeout(50)
    return None


def _safe_eval_expression(expression: str, variables: dict[str, Any]) -> Any:
    tree = ast.parse(expression, mode="eval")
    return _eval_ast_node(tree.body, variables)


def _eval_ast_node(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return variables.get(node.id)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(bool(_eval_ast_node(value, variables)) for value in node.values)
        if isinstance(node.op, ast.Or):
            return any(bool(_eval_ast_node(value, variables)) for value in node.values)
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.List):
        return [_eval_ast_node(item, variables) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast_node(item, variables) for item in node.elts)
    if isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left, variables)
        right = _eval_ast_node(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        raise ValueError("unsupported binary operator")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand, variables)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError("unsupported unary operator")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("unsupported function call")
        if node.func.id == "len" and len(node.args) == 1:
            return len(_eval_ast_node(node.args[0], variables))
        raise ValueError("unsupported function call")
    if isinstance(node, ast.Compare):
        left = _eval_ast_node(node.left, variables)
        current = left
        for operator, comparator in zip(node.ops, node.comparators, strict=False):
            right = _eval_ast_node(comparator, variables)
            if isinstance(operator, ast.Lt):
                matched = current < right
            elif isinstance(operator, ast.LtE):
                matched = current <= right
            elif isinstance(operator, ast.Gt):
                matched = current > right
            elif isinstance(operator, ast.GtE):
                matched = current >= right
            elif isinstance(operator, ast.Eq):
                matched = current == right
            elif isinstance(operator, ast.NotEq):
                matched = current != right
            else:
                raise ValueError("unsupported compare operator")
            if not matched:
                return False
            current = right
        return True
    raise ValueError("unsupported expression syntax")
