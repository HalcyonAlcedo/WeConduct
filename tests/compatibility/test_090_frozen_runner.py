from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


def test_090_frozen_preview_runner_smoke(tmp_path: Path) -> None:
    """在已构建发布目录上运行最小 preview smoke。

    构建本身不在 pytest 中执行，避免把发布构建耗时和源码回归混在一起。
    通过 ``WECONDUCT_FROZEN_EXECUTABLE`` 显式提供冻结入口后，本测试会成为
    发布门禁；未提供产物时保留为 skip，而不是假装完成了打包验证。
    """

    executable_text = os.environ.get("WECONDUCT_FROZEN_EXECUTABLE")
    if not executable_text:
        pytest.skip("未设置 WECONDUCT_FROZEN_EXECUTABLE，跳过冻结运行器 smoke")

    executable = Path(executable_text).expanduser().resolve()
    assert executable.is_file(), f"冻结入口不存在: {executable}"

    ui_dist = os.environ.get("WECONDUCT_FROZEN_UI_DIST")
    if ui_dist is None:
        ui_dist = str(executable.parent / "_internal" / "ui" / "dist")

    command = [
        str(executable),
        "preview-smoke",
        "--port",
        "0",
        "--workspace-state-path",
        str(tmp_path / "workspace-state.json"),
        "--preferences-path",
        str(tmp_path / "preferences.json"),
        "--ui-dist-path",
        str(Path(ui_dist).expanduser().resolve()),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, (
        f"冻结运行器退出码为 {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "passed"
    assert payload["failing_checks"] == []

    capabilities = subprocess.run(
        [str(executable), "operation", "host.capabilities", "--payload", "{}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=tmp_path,
    )

    assert capabilities.returncode == 0, capabilities.stderr
    capability_payload = json.loads(capabilities.stdout)
    network = capability_payload["result"]["capabilities"]["network"]
    assert network["available"] is True
    assert network["protocols"]["http2"] is True
    assert network["protocols"]["websocket"] is True
