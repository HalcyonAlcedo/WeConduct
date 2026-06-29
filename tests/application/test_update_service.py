from weconduct.application.update_service import UpdateService


def test_update_service_reports_available_update_for_newer_release() -> None:
    requested_urls: list[str] = []

    def fake_fetch(url: str, timeout_seconds: float) -> dict:
        requested_urls.append(url)
        return {
            "tag_name": "v0.7.2",
            "name": "0.7.2",
            "html_url": "https://github.com/example/weconduct/releases/tag/v0.7.2",
            "published_at": "2026-06-28T10:00:00Z",
            "body": "Bug fixes and update checks.",
            "draft": False,
            "prerelease": False,
        }

    service = UpdateService(
        current_version="0.7.1",
        repository="example/weconduct",
        fetch_release=fake_fetch,
    )

    status = service.check_for_updates(force=True)

    assert requested_urls == ["https://api.github.com/repos/example/weconduct/releases/latest"]
    assert status["current_version"] == "0.7.1"
    assert status["latest_version"] == "0.7.2"
    assert status["update_available"] is True
    assert status["check_status"] == "ok"
    assert status["check_error"] is None


def test_update_service_reuses_cached_status_when_force_is_false() -> None:
    call_count = 0

    def fake_fetch(url: str, timeout_seconds: float) -> dict:
        nonlocal call_count
        call_count += 1
        return {
            "tag_name": "v0.7.2",
            "name": "0.7.2",
            "html_url": "https://github.com/example/weconduct/releases/tag/v0.7.2",
            "published_at": "2026-06-28T10:00:00Z",
            "body": "Body",
            "draft": False,
            "prerelease": False,
        }

    service = UpdateService(
        current_version="0.7.1",
        repository="example/weconduct",
        fetch_release=fake_fetch,
        cache_ttl_seconds=21600,
    )

    first = service.check_for_updates(force=False)
    second = service.check_for_updates(force=False)

    assert call_count == 1
    assert first["last_checked_at"] == second["last_checked_at"]


def test_update_service_reports_error_for_prerelease_payload() -> None:
    def fake_fetch(url: str, timeout_seconds: float) -> dict:
        return {
            "tag_name": "v0.7.2-beta.1",
            "name": "0.7.2-beta.1",
            "html_url": "https://github.com/example/weconduct/releases/tag/v0.7.2-beta.1",
            "published_at": "2026-06-28T10:00:00Z",
            "body": "Preview",
            "draft": False,
            "prerelease": True,
        }

    service = UpdateService(
        current_version="0.7.1",
        repository="example/weconduct",
        fetch_release=fake_fetch,
    )

    status = service.check_for_updates(force=True)

    assert status["check_status"] == "error"
    assert status["check_error"] == "invalid_release_payload"
    assert status["update_available"] is False


def test_update_service_default_release_url_uses_formal_repository() -> None:
    service = UpdateService(
        current_version="0.7.1",
        repository="HalcyonAlcedo/WeConduct",
    )

    status = service.get_status()

    assert status["release_url"] == "https://github.com/HalcyonAlcedo/WeConduct/releases"
