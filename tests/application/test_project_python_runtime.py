import json
from pathlib import Path
import subprocess
import sys

import pytest

from weconduct.application.project_python_runtime import (
    ProjectPythonRuntimeManager,
    build_default_python_runtime_profile,
)


def test_python_runtime_manager_builds_stable_manifest_hash(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()

    first = manager.build_manifest(profile, project_id="demo")
    second = manager.build_manifest(profile, project_id="demo")

    assert first["manifest_hash"] == second["manifest_hash"]


def test_python_runtime_manager_hash_changes_when_requirements_change(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    changed = build_default_python_runtime_profile()
    changed["requirements_inline"] = ["requests"]

    assert manager.build_manifest(profile, project_id="demo")["manifest_hash"] != manager.build_manifest(
        changed,
        project_id="demo",
    )["manifest_hash"]


def test_python_runtime_manager_resolves_bundled_python_from_frozen_internal_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    fake_exe = tmp_path / "dist" / "WeConduct.exe"
    bundled_dir = fake_exe.parent / "_internal"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    bundled_python = bundled_dir / "python.exe"
    bundled_python.write_bytes(b"stub")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    resolved = manager._resolve_base_python_executable(profile)

    assert resolved == bundled_python


def test_python_runtime_manager_prepare_runtime_uses_bundled_python_in_frozen_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    fake_exe = tmp_path / "dist" / "WeConduct.exe"
    bundled_dir = fake_exe.parent / "_internal"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    base_executable = Path(sys.executable).resolve()
    for candidate in (
        base_executable,
        base_executable.with_name("python3.dll"),
        base_executable.with_name(f"python{sys.version_info.major}{sys.version_info.minor}.dll"),
        base_executable.with_name("base_library.zip"),
    ):
        if candidate.exists():
            (bundled_dir / candidate.name).write_bytes(candidate.read_bytes())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    report = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "ready"
    assert report["python_executable"].exists() is True


def test_python_runtime_manager_prefers_bundled_python_home_directory_in_frozen_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    fake_exe = tmp_path / "dist" / "WeConduct.exe"
    bundled_dir = fake_exe.parent / "_internal" / "bundled-python"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    bundled_python = bundled_dir / "python.exe"
    bundled_python.write_bytes(b"stub")
    bundled_zip = bundled_dir / "base_library.zip"
    bundled_zip.write_bytes(b"zip-stub")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    resolved = manager._resolve_base_python_executable(profile)

    assert resolved == bundled_python
    assert bundled_zip.exists() is True


def test_python_runtime_manager_resolves_software_cache_location(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()

    runtime_root = manager.resolve_runtime_root(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
        manifest_hash="abc123",
    )

    assert runtime_root == tmp_path / "appdata" / "python-runtimes" / "demo" / "abc123"


def test_python_runtime_manager_resolves_project_cache_location(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    profile["cache_location_mode"] = "project_cache"

    runtime_root = manager.resolve_runtime_root(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
        manifest_hash="abc123",
    )

    assert runtime_root == tmp_path / "project.data" / "python-runtime" / "abc123"


def test_python_runtime_manager_prepare_creates_materialization(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()

    report = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["runtime_root"].exists()
    assert (report["runtime_root"] / "runtime-manifest.json").exists()
    assert report["python_executable"] != Path(sys.executable)
    assert report["python_executable"].is_relative_to(report["runtime_root"])
    probe = subprocess.run(
        [str(report["python_executable"]), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0
    assert report["health_status"] == "ready"


def test_python_runtime_manager_health_check_reports_missing_before_prepare(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()

    report = manager.health_check(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "missing"


def test_python_runtime_manager_rebuild_runtime_recreates_materialization(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    project_storage_root = tmp_path / "project.data"

    first = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=project_storage_root,
    )
    manifest_file = first["runtime_root"] / "runtime-manifest.json"
    manifest_file.write_text("stale", encoding="utf-8")

    rebuilt = manager.rebuild_runtime(
        profile,
        project_id="demo",
        project_storage_root=project_storage_root,
    )

    assert rebuilt["runtime_root"] == first["runtime_root"]
    assert manifest_file.read_text(encoding="utf-8") != "stale"
    assert rebuilt["health_status"] == "ready"


def test_python_runtime_manager_health_check_reports_broken_when_manifest_missing(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    prepared = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    (prepared["runtime_root"] / "runtime-manifest.json").unlink()

    report = manager.health_check(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "broken"


def test_python_runtime_manager_health_check_reports_broken_when_python_executable_missing(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    prepared = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )
    metadata_file = prepared["runtime_root"] / "python-executable.txt"
    metadata_file.write_text(str(prepared["runtime_root"] / "missing-python.exe"), encoding="utf-8")

    report = manager.health_check(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "broken"


def test_python_runtime_manager_health_check_reports_broken_when_manifest_is_invalid_json(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    prepared = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    (prepared["runtime_root"] / "runtime-manifest.json").write_text("{broken", encoding="utf-8")

    report = manager.health_check(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "broken"


def test_python_runtime_manager_health_check_reports_stale_when_manifest_hash_mismatches(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    prepared = manager.prepare_runtime(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )
    manifest_file = prepared["runtime_root"] / "runtime-manifest.json"
    manifest_payload = prepared["runtime_root"] / "runtime-manifest.json"
    payload = manifest_payload.read_text(encoding="utf-8")
    manifest = json.loads(payload)
    manifest["manifest_hash"] = "deadbeefdeadbeef"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    report = manager.health_check(
        profile,
        project_id="demo",
        project_storage_root=tmp_path / "project.data",
    )

    assert report["health_status"] == "stale"


def test_python_runtime_manager_clear_runtime_only_removes_runtime_root(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    project_storage_root = tmp_path / "project.data"
    project_storage_root.mkdir(parents=True, exist_ok=True)
    sentinel = project_storage_root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    report = manager.prepare_runtime(profile, project_id="demo", project_storage_root=project_storage_root)
    manager.clear_runtime(profile, project_id="demo", project_storage_root=project_storage_root)

    assert not report["runtime_root"].exists()
    assert sentinel.exists()


def test_python_runtime_manager_clear_runtime_rejects_paths_outside_cache_boundary(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    outside_root = tmp_path / "outside-runtime"
    outside_root.mkdir(parents=True, exist_ok=True)
    sentinel = outside_root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    manager.resolve_runtime_root = lambda *args, **kwargs: outside_root  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        manager.clear_runtime(
            profile,
            project_id="demo",
            project_storage_root=tmp_path / "project.data",
        )

    assert sentinel.exists()


def test_python_runtime_manager_rejects_requirements_file_path_outside_project_root(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    profile["requirements_source_mode"] = "requirements_txt"
    outside_file = tmp_path / "outside-requirements.txt"
    outside_file.write_text("requests==2.32.0\n", encoding="utf-8")
    profile["requirements_file_path"] = str(outside_file.resolve())

    with pytest.raises(ValueError, match="outside project"):
        manager._collect_runtime_requirements_lines(
            profile,
            project_storage_root=tmp_path / "project.data",
        )


def test_python_runtime_manager_rejects_wheelhouse_source_path_outside_project_root(tmp_path: Path) -> None:
    manager = ProjectPythonRuntimeManager(app_data_root=tmp_path / "appdata")
    profile = build_default_python_runtime_profile()
    profile["requirements_source_mode"] = "requirements_txt"
    outside_dir = tmp_path / "external-root"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "requirements.txt"
    outside_file.write_text("requests==2.32.0\n", encoding="utf-8")
    profile["requirements_file_path"] = str(outside_file.resolve())

    with pytest.raises(ValueError, match="outside project"):
        manager._resolve_runtime_wheelhouse_source_directory(
            profile,
            project_storage_root=tmp_path / "project.data",
            runtime_root=tmp_path / "runtime.data",
        )
