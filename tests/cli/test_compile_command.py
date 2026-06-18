import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_compile_prints_graph_payload(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.json"
    source_file.write_text(
        '{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [sys.executable, "-m", "weconduct.cli.main", "compile", str(source_file)],
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
        env=env,
    )

    payload = json.loads(result.stdout)
    assert payload["graph_model"]["nodes"][0]["source_anchor_ref"] == "n1"
