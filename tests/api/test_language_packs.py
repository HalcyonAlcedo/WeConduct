"""Unit tests for the external language-pack helpers in the API server.

These cover the pure functions behind the two language endpoints:
- ``list_available_languages`` — scan ``languages/*/manifest.json``.
- ``load_language_pack`` — deep-merge every pack JSON into a namespaced tree,
  with the namespace derived from each file's path.

The design intent (see docs/i18n-migration.md): no languages are bundled;
packs live in the program directory beside preferences.json, third parties can
author them, and a broken/partial pack must degrade gracefully rather than raise.
"""

from __future__ import annotations

import json
from pathlib import Path

from weconduct.api.server import (
    list_available_languages,
    load_language_pack,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _prefs(tmp_path: Path) -> Path:
    """A preferences.json path; the languages dir is resolved as its sibling."""
    return tmp_path / "preferences.json"


def test_list_available_languages_returns_empty_when_dir_absent(tmp_path: Path) -> None:
    assert list_available_languages(_prefs(tmp_path)) == []


def test_list_available_languages_reads_manifests(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English", "author": "ACME"},
    )
    _write_json(
        languages / "ja-JP" / "manifest.json",
        {"locale": "ja-JP", "display_name": "日本語"},
    )

    result = list_available_languages(_prefs(tmp_path))

    assert result == [
        {"locale": "en-US", "display_name": "English", "author": "ACME"},
        {"locale": "ja-JP", "display_name": "日本語"},
    ]


def test_list_available_languages_skips_dirs_without_manifest(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    (languages / "not-a-pack").mkdir(parents=True)
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )

    result = list_available_languages(_prefs(tmp_path))

    assert result == [{"locale": "en-US", "display_name": "English"}]


def test_list_available_languages_falls_back_to_dir_name(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    # Manifest present but missing/blank locale + display_name → dir name used.
    _write_json(languages / "fr-FR" / "manifest.json", {"version": "1.0"})

    result = list_available_languages(_prefs(tmp_path))

    assert result == [{"locale": "fr-FR", "display_name": "fr-FR", "version": "1.0"}]


def test_load_language_pack_returns_none_for_unknown_locale(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )

    assert load_language_pack(_prefs(tmp_path), "de-DE") is None


def test_load_language_pack_namespaces_by_path(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )
    # framework.json → nested under "framework"
    _write_json(
        languages / "en-US" / "framework.json",
        {"commandBar": {"menu": {"file": "File"}}},
    )
    # nodegraph/execution.json → nested under "nodegraph.execution"
    _write_json(
        languages / "en-US" / "nodegraph" / "execution.json",
        {"pythonRun": {"label": "Python Run"}},
    )

    messages = load_language_pack(_prefs(tmp_path), "en-US")

    assert messages == {
        "framework": {"commandBar": {"menu": {"file": "File"}}},
        "nodegraph": {"execution": {"pythonRun": {"label": "Python Run"}}},
    }


def test_load_language_pack_excludes_manifest(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English", "author": "ACME"},
    )
    _write_json(
        languages / "en-US" / "framework.json",
        {"statusBar": {"ready": "Ready"}},
    )

    messages = load_language_pack(_prefs(tmp_path), "en-US")

    # The manifest must not leak into the message tree.
    assert messages == {"framework": {"statusBar": {"ready": "Ready"}}}
    assert "manifest" not in messages


def test_load_language_pack_deep_merges_sibling_files(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )
    # Two files that both contribute to the "framework" namespace.
    _write_json(
        languages / "en-US" / "framework.json",
        {"commandBar": {"menu": {"file": "File"}}},
    )
    _write_json(
        languages / "en-US" / "framework.extra.json",
        {"deep": {"key": "value"}},
    )

    messages = load_language_pack(_prefs(tmp_path), "en-US")

    # framework.json → framework.*, framework.extra.json → framework.extra.*
    assert messages["framework"]["commandBar"]["menu"]["file"] == "File"
    assert messages["framework"]["extra"]["deep"]["key"] == "value"


def test_load_language_pack_skips_malformed_json(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    _write_json(
        languages / "en-US" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )
    _write_json(
        languages / "en-US" / "framework.json",
        {"statusBar": {"ready": "Ready"}},
    )
    # A corrupt file must be skipped, not abort the whole load.
    (languages / "en-US" / "broken.json").write_text("{ not json", encoding="utf-8")

    messages = load_language_pack(_prefs(tmp_path), "en-US")

    assert messages == {"framework": {"statusBar": {"ready": "Ready"}}}


def test_load_language_pack_resolves_by_manifest_locale_not_dirname(tmp_path: Path) -> None:
    languages = tmp_path / "languages"
    # Directory name differs from the declared locale; lookup is by manifest locale.
    _write_json(
        languages / "english" / "manifest.json",
        {"locale": "en-US", "display_name": "English"},
    )
    _write_json(
        languages / "english" / "framework.json",
        {"statusBar": {"ready": "Ready"}},
    )

    assert load_language_pack(_prefs(tmp_path), "en-US") == {
        "framework": {"statusBar": {"ready": "Ready"}}
    }
    # The directory name itself is not a valid lookup key.
    assert load_language_pack(_prefs(tmp_path), "english") is None
