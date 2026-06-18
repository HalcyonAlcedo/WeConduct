import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_convert_webcontrol_prints_json_for_windows_console_unsafe_content(tmp_path: Path) -> None:
    source_file = tmp_path / "legacy.yaml"
    output_project = tmp_path / "converted.weconduct.json"
    source_file.write_text(
        """
project_info:
  name: CLI 转换测试
automation_steps:
  - step: 1
    action: set_variable
    variable_name: result
    value: "'✅ 完成'"
""".strip(),
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    env["PYTHONIOENCODING"] = "gbk"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weconduct.cli.main",
            "convert-webcontrol",
            str(source_file),
            str(output_project),
        ],
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "converted"
    assert payload["project"]["project_name"] == "CLI 转换测试"
    assert output_project.exists() is True
