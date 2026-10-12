"""Read-only production migration rehearsal into a disposable library copy.

Copies only Dev Room Markdown/index/locales, never writes the original library
or any Unity asset. Imported game sources are read-only; no push is submitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_room import DevRoomService, DEV_ROOM_PARTS
from document_library import DocumentLibraryService
from dev_room_sync import DevRoomSyncService


def digest_files(directory):
    result = {}
    for path in directory.glob('*.md'):
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def rehearse(library_root, workspace):
    original = Path(library_root).resolve().joinpath(*DEV_ROOM_PARTS)
    original_bytes = digest_files(original)
    original_index = (original / '.unity-sync.json').read_bytes()
    with tempfile.TemporaryDirectory(prefix='console-v1-media-rehearsal-') as temporary:
        base = Path(temporary).resolve(); root = base / 'library'; root.mkdir()
        target = root.joinpath(*DEV_ROOM_PARTS); target.mkdir(parents=True)
        for path in original.glob('*.md'):
            shutil.copy2(path, target / path.name)
        (target / '.unity-sync.json').write_bytes(original_index)
        if (original / '.locales').exists():
            shutil.copytree(original / '.locales', target / '.locales')
        settings = base / 'settings.json'; settings.write_text(json.dumps({'root': str(root)}), encoding='utf-8')
        library = DocumentLibraryService(settings); dev = DevRoomService(library)
        sync = DevRoomSyncService(library, workspace, dev_room=dev)
        index = json.loads(original_index); identifiers = list(index['bindings'])
        before = {identifier: dev.state(str(root), identifier, 'en')['document'] for identifier in identifiers}
        before_source = digest_files(target)
        preview = sync.preview(str(root), 'en')
        if not preview['canImport']:
            conflicts = [c for c in preview['changes'] if c['action'] == 'conflict']
            raise AssertionError('Source has real conflicts; preserved instead of automatic import: ' + json.dumps(conflicts, ensure_ascii=False))
        result = sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(root), 'language': 'en',
            'planSha256': preview['planSha256'], 'expectedIndexRevision': preview['indexRevision'], 'draftIds': []})
        after = {identifier: sync.document_state(str(root), identifier, 'en')['document'] for identifier in identifiers}
        for identifier in identifiers:
            assert before[identifier]['body'] == after[identifier]['body'], identifier + ' language body changed'
            assert before[identifier]['translationMissing'] == after[identifier]['translationMissing'], identifier + ' translation state changed'
            assert before_source[identifier + '.md'] == digest_files(target)[identifier + '.md'], identifier + ' source hash changed'
        assert original_bytes == digest_files(original), 'original library changed'
        assert (original / '.unity-sync.json').read_bytes() == original_index, 'original index changed'
        return {'status': result['status'], 'existingDocumentsPreserved': len(identifiers),
                'englishAvailableBefore': sum(not d['translationMissing'] for d in before.values()),
                'englishAvailableAfter': sum(not d['translationMissing'] for d in after.values()),
                'allOriginalSourceHashesPreserved': True, 'originalLibraryUnmodified': True,
                'importChanges': {action: sum(c['action'] == action for c in preview['changes'])
                                  for action in sorted({c['action'] for c in preview['changes']})}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library-root', required=True)
    parser.add_argument('--workspace', required=True)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.library_root, args.workspace), ensure_ascii=False))
