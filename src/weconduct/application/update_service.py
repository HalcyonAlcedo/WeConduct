from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso8601(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))


def _normalize_semver(raw_value: str) -> tuple[int, int, int]:
    text = raw_value.strip()
    if text.startswith("v"):
        text = text[1:]
    parts = text.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid semantic version: {raw_value}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _default_fetch_latest_release(url: str, timeout_seconds: float) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "WeConduct UpdateService",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("github latest release payload must be a JSON object")
    return payload


class UpdateService:
    def __init__(
        self,
        *,
        current_version: str,
        repository: str,
        fetch_release: Callable[[str, float], dict] | None = None,
        cache_ttl_seconds: int = 21600,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._current_version = current_version
        self._repository = repository
        self._fetch_release = fetch_release or _default_fetch_latest_release
        self._cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._status = self._build_idle_status()

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def check_for_updates(self, *, force: bool) -> dict:
        with self._lock:
            if not force and self._is_cache_valid_locked():
                return dict(self._status)
        status = self._perform_check()
        with self._lock:
            self._status = status
            return dict(self._status)

    def _perform_check(self) -> dict:
        api_url = f"https://api.github.com/repos/{self._repository}/releases/latest"
        try:
            payload = self._fetch_release(api_url, self._timeout_seconds)
            if not isinstance(payload, dict):
                raise ValueError("github latest release payload must be a JSON object")
            status = self._build_status_from_release(payload)
            status["last_checked_at"] = _utc_now_iso()
            status["check_status"] = "ok"
            status["check_error"] = None
            return status
        except urllib.error.HTTPError as exc:
            error_code = "rate_limited" if exc.code == 403 else "network_error"
            return self._build_error_status(error_code)
        except urllib.error.URLError:
            return self._build_error_status("network_error")
        except ValueError:
            return self._build_error_status("invalid_version")
        except RuntimeError:
            return self._build_error_status("invalid_release_payload")
        except Exception:
            return self._build_error_status("unknown_error")

    def _build_status_from_release(self, payload: dict[str, Any]) -> dict:
        if bool(payload.get("draft")) or bool(payload.get("prerelease")):
            raise RuntimeError("formal release required")
        latest_version = payload.get("tag_name") or payload.get("name")
        if not isinstance(latest_version, str) or not latest_version.strip():
            raise RuntimeError("release payload missing tag_name/name")
        normalized_latest = _normalize_semver(latest_version)
        normalized_current = _normalize_semver(self._current_version)
        status = self._build_idle_status()
        status["latest_version"] = latest_version[1:] if latest_version.startswith("v") else latest_version
        release_name = payload.get("name")
        status["release_name"] = release_name if isinstance(release_name, str) and release_name else None
        release_url = payload.get("html_url")
        if isinstance(release_url, str) and release_url.strip():
            status["release_url"] = release_url
        published_at = payload.get("published_at")
        status["published_at"] = published_at if isinstance(published_at, str) and published_at else None
        body = payload.get("body")
        status["release_notes_excerpt"] = body[:280] if isinstance(body, str) and body else None
        status["update_available"] = normalized_latest > normalized_current
        return status

    def _build_error_status(self, error_code: str) -> dict:
        status = self._build_idle_status()
        status["last_checked_at"] = _utc_now_iso()
        status["check_status"] = "error"
        status["check_error"] = error_code
        return status

    def _build_idle_status(self) -> dict:
        return {
            "source": "github_releases",
            "repository": self._repository,
            "current_version": self._current_version,
            "latest_version": None,
            "update_available": False,
            "release_name": None,
            "release_url": f"https://github.com/{self._repository}/releases",
            "published_at": None,
            "release_notes_excerpt": None,
            "last_checked_at": None,
            "check_status": "idle",
            "check_error": None,
        }

    def _is_cache_valid_locked(self) -> bool:
        if self._cache_ttl_seconds <= 0:
            return False
        last_checked_at = self._status.get("last_checked_at")
        if not isinstance(last_checked_at, str) or not last_checked_at.strip():
            return False
        try:
            last_checked = _parse_iso8601(last_checked_at)
        except ValueError:
            return False
        return (_utc_now() - last_checked) < timedelta(seconds=self._cache_ttl_seconds)
