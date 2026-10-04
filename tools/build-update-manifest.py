"""Build the public updater manifest from final, verified release artifacts.

No network, credentials, repository changes or installer modifications occur.
Run after signing and artifact verification; only the two fixed release files
are read and only public URLs, sizes and SHA-256 checksums are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console_update import MAX_RELEASE_BYTES  # noqa: E402

REPOSITORY = 'tx74666/CodexControlConsole'
ASSET_NAMES = ('CodexControlConsole-Setup-x64.exe', 'CodexControlConsole-Windows-x64.zip')
VERSION_PATTERN = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')


def plain_path(value):
    path = Path(value).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('Linked release paths are not allowed')
        if item.exists() and getattr(item.stat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse release paths are not allowed')
    return path


def identity(metadata):
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


def artifact_metadata(path):
    path = plain_path(path)
    before = path.stat()
    if not path.is_file() or before.st_nlink > 1:
        raise ValueError('Release artifacts must be regular files without links')
    if not 0 < before.st_size <= MAX_RELEASE_BYTES:
        raise ValueError('Release artifact is empty or exceeds the updater size limit')
    if path.suffix == '.zip' and not zipfile.is_zipfile(path):
        raise ValueError('Release ZIP is invalid')
    digest, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError('Release artifact changed before hashing')
        if path.suffix == '.exe' and stream.read(2) != b'MZ':
            raise ValueError('Release Setup is not a Windows executable')
        stream.seek(0)
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_RELEASE_BYTES:
                raise ValueError('Release artifact exceeds the updater size limit')
            digest.update(chunk)
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError('Release artifact changed while hashing')
    if count != before.st_size or identity(path.stat()) != identity(before):
        raise ValueError('Release artifact changed while hashing')
    return count, digest.hexdigest()


def build_manifest(version, directory):
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError('Release version must contain exactly three numeric components')
    directory = plain_path(directory)
    if not directory.is_dir():
        raise ValueError('Verified release directory does not exist')
    tag = 'v' + version
    assets = []
    for name in ASSET_NAMES:
        size, checksum = artifact_metadata(directory / name)
        assets.append({'name': name,
                       'url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}',
                       'size': size, 'sha256': checksum})
    return {'version': version, 'tag': tag,
            'releaseUrl': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
            'publishedAt': '', 'assets': assets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Three numeric components, without a v prefix')
    parser.add_argument('--directory', required=True, help='Directory containing the final verified Setup and ZIP')
    parser.add_argument('--output', help='Manifest path; defaults to DIRECTORY/update-manifest.json')
    args = parser.parse_args()
    manifest = build_manifest(args.version, args.directory)
    output = plain_path(args.output or Path(args.directory) / 'update-manifest.json')
    if output.name != 'update-manifest.json' or not output.parent.is_dir():
        raise ValueError('Output must be update-manifest.json in an existing unlinked directory')
    # Exclusive creation refuses stale or linked output instead of overwriting evidence.
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=True)
        stream.write('\n')
    print(json.dumps({'version': args.version, 'manifest': output.name, 'assetCount': len(manifest['assets'])}))


if __name__ == '__main__':
    main()
