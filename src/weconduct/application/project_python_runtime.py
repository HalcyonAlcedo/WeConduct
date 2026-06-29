from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


PYTHON_RUNTIME_INTERPRETER_STRATEGIES = {"bundled", "system", "custom_path"}
PYTHON_RUNTIME_CACHE_LOCATION_MODES = {"software_cache", "project_cache"}
PYTHON_RUNTIME_PROJECT_CACHE_MODES = {"full_venv", "wheelhouse_rebuild"}
PYTHON_RUNTIME_REQUIREMENTS_SOURCE_MODES = {"inline", "requirements_txt", "lock_file"}
PYTHON_RUNTIME_INDEX_STRATEGIES = {"default", "custom"}
PYTHON_RUNTIME_PACKAGE_EMBED_MODES = {"none", "wheelhouse_rebuild", "full_venv"}
PYTHON_RUNTIME_HEALTH_STATUSES = {"unknown", "ready", "missing", "broken", "stale"}


def _resolve_project_scoped_path(path_value: str, *, project_storage_root: Path, field_name: str) -> Path:
    candidate = Path(path_value.strip())
    project_root = project_storage_root.resolve()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"{field_name} is outside project root: {resolved}") from exc
    return resolved


def build_default_python_runtime_profile() -> dict:
    return {
        "runtime_enabled": False,
        "python_version_spec": "3.13",
        "interpreter_strategy": "bundled",
        "custom_python_path": None,
        "cache_location_mode": "software_cache",
        "project_cache_mode": "wheelhouse_rebuild",
        "requirements_source_mode": "inline",
        "requirements_inline": [],
        "requirements_file_path": None,
        "lock_file_path": None,
        "index_strategy": "default",
        "custom_index_url": None,
        "auto_prepare_on_run": True,
        "package_embed_mode": "wheelhouse_rebuild",
        "materialized_runtime_hash": None,
        "last_health_status": "unknown",
        "last_health_message": None,
    }


def normalize_python_runtime_profile(payload: dict | None, *, defaults: dict | None = None) -> dict:
    raw = payload if isinstance(payload, dict) else {}
    normalized = deepcopy(defaults) if isinstance(defaults, dict) else build_default_python_runtime_profile()

    normalized["runtime_enabled"] = _normalize_bool(
        raw.get("runtime_enabled"),
        normalized["runtime_enabled"],
    )
    normalized["python_version_spec"] = _normalize_non_empty_string(
        raw.get("python_version_spec"),
        normalized["python_version_spec"],
    )
    normalized["interpreter_strategy"] = _normalize_enum(
        raw.get("interpreter_strategy"),
        PYTHON_RUNTIME_INTERPRETER_STRATEGIES,
        normalized["interpreter_strategy"],
    )
    normalized["custom_python_path"] = _normalize_optional_string(
        raw.get("custom_python_path"),
        normalized["custom_python_path"],
    )
    normalized["cache_location_mode"] = _normalize_enum(
        raw.get("cache_location_mode"),
        PYTHON_RUNTIME_CACHE_LOCATION_MODES,
        normalized["cache_location_mode"],
    )
    normalized["project_cache_mode"] = _normalize_enum(
        raw.get("project_cache_mode"),
        PYTHON_RUNTIME_PROJECT_CACHE_MODES,
        normalized["project_cache_mode"],
    )
    normalized["requirements_source_mode"] = _normalize_enum(
        raw.get("requirements_source_mode"),
        PYTHON_RUNTIME_REQUIREMENTS_SOURCE_MODES,
        normalized["requirements_source_mode"],
    )
    normalized["requirements_inline"] = _normalize_string_list(
        raw.get("requirements_inline"),
        normalized["requirements_inline"],
    )
    normalized["requirements_file_path"] = _normalize_optional_string(
        raw.get("requirements_file_path"),
        normalized["requirements_file_path"],
    )
    normalized["lock_file_path"] = _normalize_optional_string(
        raw.get("lock_file_path"),
        normalized["lock_file_path"],
    )
    normalized["index_strategy"] = _normalize_enum(
        raw.get("index_strategy"),
        PYTHON_RUNTIME_INDEX_STRATEGIES,
        normalized["index_strategy"],
    )
    normalized["custom_index_url"] = _normalize_optional_string(
        raw.get("custom_index_url"),
        normalized["custom_index_url"],
    )
    normalized["auto_prepare_on_run"] = _normalize_bool(
        raw.get("auto_prepare_on_run"),
        normalized["auto_prepare_on_run"],
    )
    normalized["package_embed_mode"] = _normalize_enum(
        raw.get("package_embed_mode"),
        PYTHON_RUNTIME_PACKAGE_EMBED_MODES,
        normalized["package_embed_mode"],
    )
    normalized["materialized_runtime_hash"] = _normalize_optional_string(
        raw.get("materialized_runtime_hash"),
        normalized["materialized_runtime_hash"],
    )
    normalized["last_health_status"] = _normalize_enum(
        raw.get("last_health_status"),
        PYTHON_RUNTIME_HEALTH_STATUSES,
        normalized["last_health_status"],
    )
    normalized["last_health_message"] = _normalize_optional_string(
        raw.get("last_health_message"),
        normalized["last_health_message"],
    )
    return normalized


def build_default_python_runtime_preferences() -> dict:
    profile = build_default_python_runtime_profile()
    return {
        "default_python_version_spec": profile["python_version_spec"],
        "default_cache_location_mode": profile["cache_location_mode"],
        "default_project_cache_mode": profile["project_cache_mode"],
        "default_requirements_source_mode": profile["requirements_source_mode"],
        "default_package_embed_mode": profile["package_embed_mode"],
    }


def normalize_python_runtime_preferences(payload: object) -> dict:
    raw = payload if isinstance(payload, dict) else {}
    defaults = build_default_python_runtime_preferences()
    return {
        "default_python_version_spec": _normalize_non_empty_string(
            raw.get("default_python_version_spec"),
            defaults["default_python_version_spec"],
        ),
        "default_cache_location_mode": _normalize_enum(
            raw.get("default_cache_location_mode"),
            PYTHON_RUNTIME_CACHE_LOCATION_MODES,
            defaults["default_cache_location_mode"],
        ),
        "default_project_cache_mode": _normalize_enum(
            raw.get("default_project_cache_mode"),
            PYTHON_RUNTIME_PROJECT_CACHE_MODES,
            defaults["default_project_cache_mode"],
        ),
        "default_requirements_source_mode": _normalize_enum(
            raw.get("default_requirements_source_mode"),
            PYTHON_RUNTIME_REQUIREMENTS_SOURCE_MODES,
            defaults["default_requirements_source_mode"],
        ),
        "default_package_embed_mode": _normalize_enum(
            raw.get("default_package_embed_mode"),
            PYTHON_RUNTIME_PACKAGE_EMBED_MODES,
            defaults["default_package_embed_mode"],
        ),
    }


@dataclass(frozen=True)
class RuntimeHandle:
    python_executable: Path
    runtime_root: Path
    manifest_hash: str
    cache_location_mode: str
    project_cache_mode: str


class ProjectPythonRuntimeManager:
    def __init__(self, *, app_data_root: Path) -> None:
        self._app_data_root = Path(app_data_root)

    def build_manifest(self, profile: dict, *, project_id: str) -> dict:
        normalized_profile = normalize_python_runtime_profile(profile)
        manifest = {
            "project_id": project_id,
            "python_version_spec": normalized_profile["python_version_spec"],
            "interpreter_strategy": normalized_profile["interpreter_strategy"],
            "custom_python_path": normalized_profile["custom_python_path"],
            "requirements_source_mode": normalized_profile["requirements_source_mode"],
            "requirements_inline": list(normalized_profile["requirements_inline"]),
            "requirements_file_path": normalized_profile["requirements_file_path"],
            "lock_file_path": normalized_profile["lock_file_path"],
            "index_strategy": normalized_profile["index_strategy"],
            "custom_index_url": normalized_profile["custom_index_url"],
            "project_cache_mode": normalized_profile["project_cache_mode"],
        }
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        manifest_hash = sha256(manifest_json.encode("utf-8")).hexdigest()[:16]
        return {**manifest, "manifest_hash": manifest_hash}

    def resolve_runtime_root(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
        manifest_hash: str,
    ) -> Path:
        normalized_profile = normalize_python_runtime_profile(profile)
        if normalized_profile["cache_location_mode"] == "project_cache":
            return Path(project_storage_root) / "python-runtime" / manifest_hash
        return self._app_data_root / "python-runtimes" / project_id / manifest_hash

    def prepare_runtime(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
    ) -> dict:
        manifest = self.build_manifest(profile, project_id=project_id)
        runtime_root = self.resolve_runtime_root(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
            manifest_hash=manifest["manifest_hash"],
        )
        runtime_root.mkdir(parents=True, exist_ok=True)
        venv_root = runtime_root / "venv"
        base_python_executable = self._resolve_base_python_executable(profile)
        python_relative_path = self._build_runtime_python_relative_path()
        python_executable = runtime_root / python_relative_path
        if not python_executable.exists():
            self._create_virtual_environment(
                base_python_executable=base_python_executable,
                venv_root=venv_root,
            )
        _write_runtime_sitecustomize(
            _build_runtime_site_packages_root(venv_root),
            blocked_sys_paths=_collect_blocked_runtime_sys_paths(
                base_python_executable=base_python_executable,
                venv_root=venv_root,
            ),
        )
        (runtime_root / "runtime-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        requirements_lines = self._collect_runtime_requirements_lines(
            profile,
            project_storage_root=project_storage_root,
            runtime_root=runtime_root,
        )
        if requirements_lines:
            (runtime_root / "requirements.txt").write_text(
                "\n".join(requirements_lines) + "\n",
                encoding="utf-8",
            )
        (runtime_root / "python-executable.txt").write_text(
            python_relative_path.as_posix(),
            encoding="utf-8",
        )
        self._install_runtime_requirements(
            normalized_profile=normalize_python_runtime_profile(profile),
            project_storage_root=project_storage_root,
            runtime_root=runtime_root,
            python_executable=python_executable,
            requirements_lines=requirements_lines,
        )
        return self.health_check(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
        )

    def health_check(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
    ) -> dict:
        manifest = self.build_manifest(profile, project_id=project_id)
        runtime_root = self.resolve_runtime_root(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
            manifest_hash=manifest["manifest_hash"],
        )
        manifest_file = runtime_root / "runtime-manifest.json"
        if not runtime_root.exists():
            return self._build_runtime_report(
                handle=self._build_runtime_handle(
                    profile=profile,
                    project_cache_mode=manifest["project_cache_mode"],
                    runtime_root=runtime_root,
                    manifest_hash=manifest["manifest_hash"],
                    python_executable=Path(sys.executable),
                ),
                health_status="missing",
                health_message="runtime root missing",
            )
        if not manifest_file.exists():
            return self._build_runtime_report(
                handle=self._build_runtime_handle(
                    profile=profile,
                    project_cache_mode=manifest["project_cache_mode"],
                    runtime_root=runtime_root,
                    manifest_hash=manifest["manifest_hash"],
                    python_executable=Path(sys.executable),
                ),
                health_status="broken",
                health_message="runtime manifest missing",
            )
        manifest_payload = self._read_manifest_payload(manifest_file)
        if manifest_payload is None:
            return self._build_runtime_report(
                handle=self._build_runtime_handle(
                    profile=profile,
                    project_cache_mode=manifest["project_cache_mode"],
                    runtime_root=runtime_root,
                    manifest_hash=manifest["manifest_hash"],
                    python_executable=Path(sys.executable),
                ),
                health_status="broken",
                health_message="runtime manifest unreadable",
            )
        python_executable = self._read_materialized_python_executable(runtime_root)
        handle = self._build_runtime_handle(
            profile=profile,
            project_cache_mode=manifest["project_cache_mode"],
            runtime_root=runtime_root,
            manifest_hash=manifest["manifest_hash"],
            python_executable=python_executable,
        )
        if python_executable is None:
            return self._build_runtime_report(
                handle=handle,
                health_status="broken",
                health_message="python executable metadata missing",
            )
        if not python_executable.exists():
            return self._build_runtime_report(
                handle=handle,
                health_status="broken",
                health_message="python executable missing",
            )
        if not self._can_launch_python(python_executable):
            return self._build_runtime_report(
                handle=handle,
                health_status="broken",
                health_message="python executable not launchable",
            )
        requirements_lines = self._collect_runtime_requirements_lines(
            profile,
            project_storage_root=project_storage_root,
            runtime_root=runtime_root,
        )
        if requirements_lines:
            expected_requirements_hash = self._build_requirements_hash(requirements_lines)
            installed_requirements_hash = self._read_installed_requirements_hash(runtime_root)
            if installed_requirements_hash is None:
                return self._build_runtime_report(
                    handle=handle,
                    health_status="broken",
                    health_message="python requirements not installed",
                )
            if installed_requirements_hash != expected_requirements_hash:
                return self._build_runtime_report(
                    handle=handle,
                    health_status="stale",
                    health_message="python requirements install hash mismatch",
                )
        stored_manifest_hash = manifest_payload.get("manifest_hash")
        if stored_manifest_hash != manifest["manifest_hash"]:
            return self._build_runtime_report(
                handle=handle,
                health_status="stale",
                health_message="manifest hash mismatch",
            )
        expected_blocked_sys_paths = _collect_blocked_runtime_sys_paths(
            base_python_executable=python_executable,
            venv_root=runtime_root / "venv",
        )
        if not _runtime_sitecustomize_matches(
            _build_runtime_site_packages_root(runtime_root / "venv"),
            blocked_sys_paths=expected_blocked_sys_paths,
        ):
            return self._build_runtime_report(
                handle=handle,
                health_status="stale",
                health_message="runtime sitecustomize is missing or outdated",
            )
        return self._build_runtime_report(handle=handle, health_status="ready", health_message=None)

    def rebuild_runtime(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
    ) -> dict:
        self.clear_runtime(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
        )
        return self.prepare_runtime(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
        )

    def clear_runtime(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
    ) -> dict:
        manifest = self.build_manifest(profile, project_id=project_id)
        runtime_root = self.resolve_runtime_root(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
            manifest_hash=manifest["manifest_hash"],
        )
        self._assert_runtime_root_within_boundary(
            profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
            runtime_root=runtime_root,
        )
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
        handle = self._build_runtime_handle(
            profile=profile,
            project_cache_mode=manifest["project_cache_mode"],
            runtime_root=runtime_root,
            manifest_hash=manifest["manifest_hash"],
            python_executable=self._read_materialized_python_executable(runtime_root) or Path(sys.executable),
        )
        return self._build_runtime_report(handle=handle, health_status="missing", health_message="runtime cleared")

    def _build_runtime_report(
        self,
        *,
        handle: RuntimeHandle,
        health_status: str,
        health_message: str | None,
    ) -> dict:
        return {
            "runtime_root": handle.runtime_root,
            "python_executable": handle.python_executable,
            "manifest_hash": handle.manifest_hash,
            "cache_location_mode": handle.cache_location_mode,
            "project_cache_mode": handle.project_cache_mode,
            "runtime_handle": handle,
            "health_status": health_status,
            "health_message": health_message,
        }

    def _build_runtime_handle(
        self,
        *,
        profile: dict,
        project_cache_mode: str,
        runtime_root: Path,
        manifest_hash: str,
        python_executable: Path | None,
    ) -> RuntimeHandle:
        normalized_profile = normalize_python_runtime_profile(profile)
        return RuntimeHandle(
            python_executable=python_executable or Path(sys.executable),
            runtime_root=runtime_root,
            manifest_hash=manifest_hash,
            cache_location_mode=normalized_profile["cache_location_mode"],
            project_cache_mode=project_cache_mode,
        )

    def _read_manifest_payload(self, manifest_file: Path) -> dict | None:
        try:
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def _read_materialized_python_executable(self, runtime_root: Path) -> Path | None:
        metadata_file = runtime_root / "python-executable.txt"
        try:
            raw_value = metadata_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw_value:
            return None
        candidate = Path(raw_value)
        if candidate.is_absolute():
            return candidate
        return (runtime_root / candidate).resolve()

    def export_runtime_bundle(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
        package_embed_mode: str,
    ) -> dict:
        normalized_profile = normalize_python_runtime_profile(profile)
        mode = package_embed_mode.strip() if isinstance(package_embed_mode, str) else "none"
        if mode == "none":
            raise ValueError(
                "python runtime bundle export requires package_embed_mode other than none"
            )
        if mode == "wheelhouse_rebuild":
            manifest = self.build_manifest(normalized_profile, project_id=project_id)
            runtime_root = self.resolve_runtime_root(
                normalized_profile,
                project_id=project_id,
                project_storage_root=project_storage_root,
                manifest_hash=manifest["manifest_hash"],
            )
            requirements_lines = self._collect_runtime_requirements_lines(
                normalized_profile,
                project_storage_root=project_storage_root,
                runtime_root=runtime_root,
            )
            archive_entries: dict[str, bytes] = {
                "wheelhouse/requirements.txt": (
                    ("\n".join(requirements_lines) + "\n").encode("utf-8")
                    if requirements_lines
                    else b""
                ),
                "wheelhouse/runtime-manifest.json": json.dumps(
                    self.build_manifest(normalized_profile, project_id=project_id),
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            }
            wheelhouse_source = self._resolve_runtime_wheelhouse_source_directory(
                normalized_profile,
                project_storage_root=project_storage_root,
                runtime_root=runtime_root,
            )
            if wheelhouse_source is not None:
                for file_path in wheelhouse_source.rglob("*"):
                    if not file_path.is_file():
                        continue
                    relative_path = file_path.relative_to(wheelhouse_source).as_posix()
                    archive_entries[f"wheelhouse/{relative_path}"] = file_path.read_bytes()
            return {
                "bundle_root": "wheelhouse",
                "archive_entries": archive_entries,
            }

        report = self.health_check(
            normalized_profile,
            project_id=project_id,
            project_storage_root=project_storage_root,
        )
        if report["health_status"] != "ready":
            report = self.prepare_runtime(
                normalized_profile,
                project_id=project_id,
                project_storage_root=project_storage_root,
            )
        if report["health_status"] != "ready":
            raise ValueError(
                "python runtime is not ready for full_venv export: "
                f"{report['health_message'] or report['health_status']}"
            )
        runtime_root = Path(report["runtime_root"])
        archive_entries = {}
        for file_path in runtime_root.rglob("*"):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(runtime_root).as_posix()
            archive_entries[f"full-venv/{relative_path}"] = file_path.read_bytes()
        return {
            "bundle_root": "full-venv",
            "archive_entries": archive_entries,
        }

    def _build_runtime_python_relative_path(self) -> Path:
        if os.name == "nt":
            return Path("venv") / "Scripts" / "python.exe"
        return Path("venv") / "bin" / "python"

    def _resolve_base_python_executable(self, profile: dict) -> Path:
        normalized_profile = normalize_python_runtime_profile(profile)
        interpreter_strategy = normalized_profile.get("interpreter_strategy", "bundled")
        if interpreter_strategy == "custom_path":
            custom_python_path = normalized_profile.get("custom_python_path")
            if not isinstance(custom_python_path, str) or not custom_python_path.strip():
                raise ValueError("python runtime custom interpreter path is required")
            resolved_custom_python = Path(custom_python_path.strip()).expanduser().resolve(strict=False)
            if not resolved_custom_python.exists():
                raise ValueError(
                    f"python runtime custom interpreter not found: {resolved_custom_python}"
                )
            return resolved_custom_python

        if interpreter_strategy == "system":
            return self._resolve_system_python_executable()

        if getattr(sys, "frozen", False):
            bundled_candidates = [
                Path(sys.executable).resolve(strict=False).parent / "_internal" / "bundled-python" / "python.exe",
                Path(sys.executable).resolve(strict=False).parent / "_internal" / "python.exe",
                Path(sys.executable).resolve(strict=False).parent / "python.exe",
            ]
            meipass = getattr(sys, "_MEIPASS", None)
            if isinstance(meipass, str) and meipass.strip():
                bundled_candidates.append(Path(meipass).resolve(strict=False) / "python.exe")
            for candidate in bundled_candidates:
                if candidate.exists():
                    return candidate
            raise ValueError(
                "python runtime bundled interpreter not found; expected python.exe beside the packaged application"
            )

        return self._resolve_system_python_executable()

    def _resolve_system_python_executable(self) -> Path:
        executable = getattr(sys, "_base_executable", None) or sys.executable
        if isinstance(executable, str) and executable.strip():
            resolved = Path(executable).expanduser().resolve(strict=False)
            if resolved.exists():
                return resolved
        discovered = shutil.which("python")
        if discovered:
            return Path(discovered).expanduser().resolve(strict=False)
        raise ValueError("python runtime base interpreter is unavailable")

    def _create_virtual_environment(self, *, base_python_executable: Path, venv_root: Path) -> None:
        command = [
            str(base_python_executable),
            "-m",
            "venv",
            str(venv_root),
        ]
        if venv_root.exists():
            command.insert(3, "--clear")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"python runtime venv creation failed: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise ValueError(f"python runtime venv creation failed: {detail}")

    def _collect_runtime_requirements_lines(
        self,
        profile: dict,
        *,
        project_storage_root: Path,
        runtime_root: Path | None = None,
    ) -> list[str]:
        normalized_profile = normalize_python_runtime_profile(profile)
        source_mode = normalized_profile.get("requirements_source_mode", "inline")
        if source_mode == "inline":
            return list(normalized_profile.get("requirements_inline", []))
        relative_path = None
        if source_mode == "requirements_txt":
            relative_path = normalized_profile.get("requirements_file_path")
        elif source_mode == "lock_file":
            relative_path = normalized_profile.get("lock_file_path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            return []
        candidate = _resolve_project_scoped_path(
            relative_path,
            project_storage_root=project_storage_root,
            field_name="requirements file path",
        )
        try:
            return [
                line.strip()
                for line in candidate.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            fallback_candidates: list[Path] = []
            if runtime_root is not None:
                fallback_candidates.append(runtime_root / "requirements.txt")
                fallback_candidates.append(runtime_root / "wheelhouse" / candidate.name)
            for fallback in fallback_candidates:
                try:
                    return [
                        line.strip()
                        for line in fallback.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                except OSError:
                    continue
            return []

    def _build_requirements_hash(self, requirements_lines: list[str]) -> str:
        payload = "\n".join(requirements_lines).encode("utf-8")
        return sha256(payload).hexdigest()

    def _read_installed_requirements_hash(self, runtime_root: Path) -> str | None:
        marker_path = runtime_root / "installed-requirements.hash"
        try:
            value = marker_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def _write_installed_requirements_hash(
        self,
        runtime_root: Path,
        requirements_lines: list[str],
    ) -> None:
        (runtime_root / "installed-requirements.hash").write_text(
            self._build_requirements_hash(requirements_lines),
            encoding="utf-8",
        )

    def _resolve_runtime_wheelhouse_source_directory(
        self,
        profile: dict,
        *,
        project_storage_root: Path,
        runtime_root: Path,
    ) -> Path | None:
        runtime_wheelhouse = runtime_root / "wheelhouse"
        if runtime_wheelhouse.exists() and any(runtime_wheelhouse.rglob("*")):
            return runtime_wheelhouse
        candidate_directories: list[Path] = []
        normalized_profile = normalize_python_runtime_profile(profile)
        source_mode = normalized_profile.get("requirements_source_mode", "inline")
        if source_mode == "requirements_txt":
            relative_path = normalized_profile.get("requirements_file_path")
        elif source_mode == "lock_file":
            relative_path = normalized_profile.get("lock_file_path")
        else:
            relative_path = None
        if isinstance(relative_path, str) and relative_path.strip():
            requirements_path = _resolve_project_scoped_path(
                relative_path,
                project_storage_root=project_storage_root,
                field_name="wheelhouse source path",
            )
            candidate_directories.append(requirements_path.parent / "wheelhouse")
        candidate_directories.append(project_storage_root / "wheelhouse")
        for candidate in candidate_directories:
            if candidate.exists() and any(candidate.rglob("*")):
                return candidate
        return None

    def _materialize_runtime_wheelhouse(
        self,
        *,
        source_directory: Path,
        runtime_root: Path,
    ) -> Path:
        target_directory = runtime_root / "wheelhouse"
        if source_directory.resolve(strict=False) == target_directory.resolve(strict=False):
            return target_directory
        if target_directory.exists():
            shutil.rmtree(target_directory, ignore_errors=True)
        shutil.copytree(source_directory, target_directory, dirs_exist_ok=True)
        return target_directory

    def _install_runtime_requirements(
        self,
        *,
        normalized_profile: dict,
        project_storage_root: Path,
        runtime_root: Path,
        python_executable: Path,
        requirements_lines: list[str],
    ) -> None:
        if not requirements_lines:
            stale_marker = runtime_root / "installed-requirements.hash"
            if stale_marker.exists():
                stale_marker.unlink(missing_ok=True)
            return
        requirements_file = runtime_root / "requirements.txt"
        command = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements_file),
        ]
        wheelhouse_source = self._resolve_runtime_wheelhouse_source_directory(
            normalized_profile,
            project_storage_root=project_storage_root,
            runtime_root=runtime_root,
        )
        if wheelhouse_source is not None:
            materialized_wheelhouse = self._materialize_runtime_wheelhouse(
                source_directory=wheelhouse_source,
                runtime_root=runtime_root,
            )
            command[4:4] = ["--no-index", "--find-links", str(materialized_wheelhouse)]
        elif normalized_profile.get("index_strategy") == "custom":
            custom_index_url = normalized_profile.get("custom_index_url")
            if isinstance(custom_index_url, str) and custom_index_url.strip():
                command[4:4] = ["--index-url", custom_index_url.strip()]
        try:
            result = subprocess.run(
                command,
                cwd=str(project_storage_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"python runtime dependency install failed: {exc}") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            raise ValueError(f"python runtime dependency install failed: {detail}")
        self._write_installed_requirements_hash(runtime_root, requirements_lines)

    def _can_launch_python(self, python_executable: Path) -> bool:
        try:
            result = subprocess.run(
                [str(python_executable), "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def _assert_runtime_root_within_boundary(
        self,
        profile: dict,
        *,
        project_id: str,
        project_storage_root: Path,
        runtime_root: Path,
    ) -> None:
        normalized_profile = normalize_python_runtime_profile(profile)
        if normalized_profile["cache_location_mode"] == "project_cache":
            boundary_root = Path(project_storage_root).resolve(strict=False) / "python-runtime"
        else:
            boundary_root = (self._app_data_root / "python-runtimes" / project_id).resolve(strict=False)
        resolved_runtime_root = Path(runtime_root).resolve(strict=False)
        try:
            relative_path = resolved_runtime_root.relative_to(boundary_root)
        except ValueError as exc:
            raise ValueError(f"runtime root escaped cache boundary: {resolved_runtime_root}") from exc
        if not relative_path.parts:
            raise ValueError(f"refusing to clear cache boundary root directly: {resolved_runtime_root}")


def _build_runtime_site_packages_root(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Lib" / "site-packages"
    return venv_root / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def _collect_blocked_runtime_sys_paths(
    *,
    base_python_executable: Path,
    venv_root: Path | None = None,
) -> list[Path]:
    blocked_paths: list[Path] = []
    resolved_parent = base_python_executable.resolve(strict=False).parent
    if resolved_parent.name.lower() == "_internal":
        blocked_paths.append(resolved_parent)
    venv_home = _read_venv_home_directory(venv_root)
    if venv_home is not None and venv_home.name.lower() == "_internal":
        blocked_paths.append(venv_home)
    deduped_paths: list[Path] = []
    seen: set[str] = set()
    for candidate in blocked_paths:
        normalized = os.path.normcase(os.path.abspath(str(candidate.resolve(strict=False))))
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped_paths.append(candidate)
    return deduped_paths


def _read_venv_home_directory(venv_root: Path | None) -> Path | None:
    if venv_root is None:
        return None
    pyvenv_cfg = Path(venv_root) / "pyvenv.cfg"
    try:
        lines = pyvenv_cfg.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().lower() != "home":
            continue
        home_value = value.strip()
        if not home_value:
            return None
        return Path(home_value).expanduser().resolve(strict=False)
    return None


def _write_runtime_sitecustomize(
    target_directory: Path,
    *,
    blocked_sys_paths: list[Path],
) -> None:
    target_directory.mkdir(parents=True, exist_ok=True)
    sitecustomize_path = target_directory / "sitecustomize.py"
    script = _build_runtime_sitecustomize_content(blocked_sys_paths=blocked_sys_paths)
    sitecustomize_path.write_text(script, encoding='utf-8')


def _runtime_sitecustomize_matches(
    target_directory: Path,
    *,
    blocked_sys_paths: list[Path],
) -> bool:
    sitecustomize_path = Path(target_directory) / "sitecustomize.py"
    try:
        current = sitecustomize_path.read_text(encoding="utf-8")
    except OSError:
        return False
    expected = _build_runtime_sitecustomize_content(blocked_sys_paths=blocked_sys_paths)
    return current == expected


def _build_runtime_sitecustomize_content(*, blocked_sys_paths: list[Path]) -> str:
    normalized_paths = sorted(
        {
            os.path.normcase(os.path.abspath(str(Path(path).resolve(strict=False))))
            for path in blocked_sys_paths
        }
    )
    return (
        "from __future__ import annotations\n\n"
        "import os\n"
        "import sys\n\n"
        f"_BLOCKED_SYS_PATHS = {normalized_paths!r}\n\n"
        "def _normalize_runtime_path(value: str) -> str:\n"
        "    return os.path.normcase(os.path.abspath(value))\n\n"
        "if _BLOCKED_SYS_PATHS:\n"
        "    sys.path = [\n"
        "        entry\n"
        "        for entry in sys.path\n"
        "        if _normalize_runtime_path(entry) not in _BLOCKED_SYS_PATHS\n"
        "    ]\n"
    )


def _normalize_non_empty_string(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _normalize_optional_string(value: object, default: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _normalize_enum(value: object, allowed_values: set[str], default: str) -> str:
    if value in allowed_values:
        return str(value)
    return default


def _normalize_string_list(value: object, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default
