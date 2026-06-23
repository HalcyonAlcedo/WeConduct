
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
from pathlib import Path

from weconduct.api import build_api_server


def _request_json(url: str, *, method: str = 'GET', payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode('utf-8'))


def test_api_exposes_updates_and_resets_preferences_document(tmp_path: Path) -> None:
    server = build_api_server(
        host='127.0.0.1',
        port=0,
        workspace_state_path=tmp_path / 'workspace-state.json',
        preferences_path=tmp_path / 'preferences.json',
        ui_dist_path=tmp_path / 'ui-dist',
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f'http://127.0.0.1:{server.server_address[1]}'

        payload = _request_json(f'{base_url}/api/workbench/preferences')
        assert payload['preferences']['program_settings']['language'] == 'zh-CN'
        assert payload['preferences']['compile_settings']['block_on_disabled_components'] is True

        updated = _request_json(
            f'{base_url}/api/workbench/preferences',
            method='POST',
            payload={
                'section': 'program_settings',
                'values': {
                    'language': 'en-US',
                    'theme': 'dark',
                },
            },
        )
        assert updated['preferences']['program_settings']['language'] == 'en-US'
        assert updated['preferences']['program_settings']['theme'] == 'dark'

        persisted = _request_json(f'{base_url}/api/workbench/preferences')
        assert persisted['preferences']['program_settings']['language'] == 'en-US'
        assert persisted['preferences']['program_settings']['theme'] == 'dark'

        reset = _request_json(f'{base_url}/api/workbench/preferences/reset', method='POST', payload={})
        assert reset['preferences']['program_settings']['language'] == 'zh-CN'
        assert reset['preferences']['program_settings']['theme'] == 'light'

        reset_persisted = _request_json(f'{base_url}/api/workbench/preferences')
        assert reset_persisted['preferences']['program_settings']['language'] == 'zh-CN'
        assert reset_persisted['preferences']['program_settings']['theme'] == 'light'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_api_supports_preferences_preview_and_high_risk_confirmation(tmp_path: Path) -> None:
    server = build_api_server(
        host='127.0.0.1',
        port=0,
        workspace_state_path=tmp_path / 'workspace-state.json',
        preferences_path=tmp_path / 'preferences.json',
        ui_dist_path=tmp_path / 'ui-dist',
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f'http://127.0.0.1:{server.server_address[1]}'

        preview = _request_json(
            f'{base_url}/api/workbench/preferences/preview',
            method='POST',
            payload={
                'section': 'security_settings',
                'values': {
                    'allow_external_programs': True,
                    'file_access_scope': 'allow_all',
                },
            },
        )
        assert preview['confirmation_required'] is True
        assert preview['high_risk_changes'] == [
            {
                'field': 'allow_external_programs',
                'from': False,
                'to': True,
                'reason': 'enables external program execution',
            },
            {
                'field': 'file_access_scope',
                'from': 'restricted',
                'to': 'allow_all',
                'reason': 'allows file access outside configured directories',
            },
        ]

        denied_request = urllib.request.Request(
            f'{base_url}/api/workbench/preferences',
            data=json.dumps(
                {
                    'section': 'security_settings',
                    'values': {
                        'allow_external_programs': True,
                    },
                }
            ).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            urllib.request.urlopen(denied_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode('utf-8'))
            assert exc.code == 409
            assert payload['error'] == 'high_risk_confirmation_required'
            assert payload['requires_confirmation'] is True
            assert payload['high_risk_changes'] == [
                {
                    'field': 'allow_external_programs',
                    'from': False,
                    'to': True,
                    'reason': 'enables external program execution',
                }
            ]
        else:
            raise AssertionError('expected HTTPError for missing high-risk confirmation')

        confirmed = _request_json(
            f'{base_url}/api/workbench/preferences',
            method='POST',
            payload={
                'section': 'security_settings',
                'confirm_high_risk': True,
                'values': {
                    'allow_external_programs': True,
                    'file_access_scope': 'allow_all',
                },
            },
        )
        assert confirmed['preferences']['security_settings']['allow_external_programs'] is True
        assert confirmed['preferences']['security_settings']['file_access_scope'] == 'allow_all'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
