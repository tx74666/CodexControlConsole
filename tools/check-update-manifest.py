"""Isolated release-manifest checks; no network or real installation is used."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manifest_builder', ROOT / 'tools/build-update-manifest.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
from console_update import ConsoleUpdateService, MAX_RELEASE_BYTES  # noqa: E402


def reject(action, reason):
    try:
        action()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError(reason)


def main():
    assert builder.MAX_RELEASE_BYTES == MAX_RELEASE_BYTES
    with tempfile.TemporaryDirectory(prefix='console-manifest-check-') as temporary:
        root = Path(temporary)
        release = root / 'verified packages'
        release.mkdir()
        setup = release / builder.ASSET_NAMES[0]
        archive = release / builder.ASSET_NAMES[1]
        setup.write_bytes(b'MZ' + bytes(range(128)))
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('Codex Console/_internal/app-manifest.json', json.dumps({'version': '1.0.34', 'installMode': 'installed'}))
        original = {path.name: path.read_bytes() for path in (setup, archive)}
        payload = builder.build_manifest('1.0.34', release)
        assert set(payload) == {'version', 'tag', 'releaseUrl', 'publishedAt', 'assets'}
        assert payload['tag'] == 'v1.0.34' and payload['publishedAt'] == ''
        assert payload['releaseUrl'] == 'https://github.com/tx74666/CodexControlConsole/releases/tag/v1.0.34'
        assert [asset['name'] for asset in payload['assets']] == list(builder.ASSET_NAMES)
        for asset in payload['assets']:
            content = original[asset['name']]
            assert set(asset) == {'name', 'url', 'size', 'sha256'}
            assert asset['size'] == len(content)
            assert asset['sha256'] == hashlib.sha256(content).hexdigest()
            assert asset['url'] == f"https://github.com/tx74666/CodexControlConsole/releases/download/v1.0.34/{asset['name']}"
        assert str(root) not in json.dumps(payload)
        for invalid in ('', 'v1.0.34', '1.0', '1.0.34-beta', '1.0.34\n', '１.0.34', '../1.0.34', '1.0.34/secret'):
            reject(lambda value=invalid: builder.build_manifest(value, release), 'Invalid version was accepted')
        assert builder.build_manifest('10.22.345', release)['tag'] == 'v10.22.345'
        reject(lambda: builder.build_manifest('1.0.34', root / 'missing'), 'Missing directory was accepted')
        with patch.object(builder, 'MAX_RELEASE_BYTES', 8):
            reject(lambda: builder.build_manifest('1.0.34', release), 'Oversized release was accepted')
        setup.write_bytes(b'')
        reject(lambda: builder.build_manifest('1.0.34', release), 'Empty Setup was accepted')
        setup.write_bytes(b'not-a-Windows-executable')
        reject(lambda: builder.build_manifest('1.0.34', release), 'Invalid Setup was accepted')
        setup.write_bytes(original[setup.name])
        archive.write_bytes(b'not-a-zip')
        reject(lambda: builder.build_manifest('1.0.34', release), 'Invalid ZIP was accepted')
        archive.write_bytes(original[archive.name])
        original_setup = release / 'unchanged-setup.exe'
        setup.rename(original_setup)
        try:
            os.link(original_setup, setup)
            reject(lambda: builder.build_manifest('1.0.34', release), 'Hard-linked Setup was accepted')
        finally:
            if setup.exists():
                setup.unlink()
            original_setup.rename(setup)
        with patch.object(Path, 'is_symlink', lambda path: path == setup):
            reject(lambda: builder.build_manifest('1.0.34', release), 'Linked Setup was accepted')
        command = [sys.executable, '-B', str(ROOT / 'tools/build-update-manifest.py'), '--version', '1.0.34', '--directory', str(release)]
        generated = subprocess.run(command, capture_output=True, text=True, check=True)
        assert json.loads(generated.stdout)['manifest'] == 'update-manifest.json'
        manifest_file = release / 'update-manifest.json'
        assert json.loads(manifest_file.read_text(encoding='utf-8')) == payload
        again = subprocess.run(command, capture_output=True, text=True)
        assert again.returncode != 0 and json.loads(manifest_file.read_text(encoding='utf-8')) == payload
        assert {path.name: path.read_bytes() for path in (setup, archive)} == original

        # The currently installed updater can consume the public manifest even
        # when GitHub's API fallback is unavailable, without injecting its cache.
        service = ConsoleUpdateService(root / 'app', root / 'data',
            {'version': '1.0.33', 'repository': builder.REPOSITORY, 'installMode': 'installed'}, 'developer')
        requests = []
        def request(url, **kwargs):
            requests.append(url)
            assert url == 'https://github.com/tx74666/CodexControlConsole/releases/latest/download/update-manifest.json'
            return io.BytesIO(json.dumps(payload).encode('utf-8'))
        with patch.object(service, '_request', request), patch.object(service, '_fetch_latest_api', side_effect=AssertionError('API fallback must not run')):
            status = service.check()
        assert len(requests) == 1 and status['latestVersion'] == '1.0.34' and status['available']
        accepted = service._release_asset(service._read_state(), builder.ASSET_NAMES[0])
        assert accepted['sha256'] == payload['assets'][0]['sha256'] and status['assetAvailable']

    workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    assert workflow.index('Defender scan release artifacts') < workflow.index('Build verified updater manifest') < workflow.index('Verify release downloads') < workflow.index('Publish GitHub Release')
    assert 'python tools/build-update-manifest.py --version "$env:RELEASE_VERSION" --directory dist' in workflow
    assert '            "update-manifest.json"' in workflow and '            dist/update-manifest.json' in workflow
    print('PASS verified update manifest: fixed release URLs, exact hashes, version/size/link boundaries, unchanged binaries, exclusive output, manifest-first updater and pipeline publication')


if __name__ == '__main__':
    main()
