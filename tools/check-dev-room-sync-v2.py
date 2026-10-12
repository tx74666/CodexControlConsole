"""Isolated v2 backend contracts; simulated receipts never claim Editor execution.

All mutations target TemporaryDirectory fixtures. Optional --inventory-workspace
reads only the existing bounded source inventory and reports its real image pins.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_room import DevRoomService, DEV_ROOM_PARTS
from document_library import DocumentLibraryService
from dev_room_sync import DevRoomSyncService, DevRoomSyncConflict, INDEX_PARTS, NAMESPACE, _json_bytes, _sha
import dev_room_media as media
import unity_dev_room_documents as source


def image_bytes(color='blue'):
    from PIL import Image
    buffer = BytesIO()
    Image.new('RGB', (3, 2), color).save(buffer, format='PNG')
    return buffer.getvalue()


def build_fixture(base):
    """Small real Unity YAML fixture, useful for isolated HTTP/browser checks."""
    root = Path(base)
    def write(path, raw):
        path = root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if isinstance(raw, bytes) else raw.encode('utf-8'))
    def metadata(path, guid, user=''):
        write(path + '.meta', 'fileFormatVersion: 2\nguid: ' + guid + '\nNativeFormatImporter:\n  userData: ' + user + '\n')
    def asset(class_name, script_guid, content, file_id=11400000, header=True):
        return (('%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n' if header else '') +
                '--- !u!114 &' + str(file_id) + '\nMonoBehaviour:\n  m_Script: {fileID: 11500000, guid: ' + script_guid + ', type: 3}\n' +
                '  m_EditorClassIdentifier: Unity.RandomRealm.Gameplay.Builds::Unity.RandomRealm.Gameplay.' + class_name + '\n' + content)
    def doc(identifier, title):
        return ('  m_Id: ' + identifier + '\n  m_Title: ' + title + '\n  m_Category: 0\n  m_DisplayOrder: 1\n'
                '  m_Summary: Existing content summary\n  m_UpdatedAt: 2026-10-12\n  m_SourceReference: fixture\n  m_SourceUpdatedAt: 2026-10-09T01:10:30.521Z\n'
                '  m_Sections:\n  - m_Title: Existing section\n    m_Body: Existing body\n'
                '    m_Image: {fileID: 2800000, guid: ' + 'd' * 32 + ', type: 3}\n'
                '    m_ImageResourcePath: UI/DevsRealm/Before\n    m_ImageCaption: Original caption\n')
    write('ProjectSettings/ProjectVersion.txt', 'm_EditorVersion: 6000.0.1f1\n')
    (root / source.DOCUMENT_ROOTS[0]).mkdir(parents=True)
    (root / source.DOCUMENT_ROOTS[1]).mkdir(parents=True)
    global_path = source.DOCUMENT_ROOTS[1] + '/Fixture.asset'
    write(global_path, asset('DevsRealmDocumentAsset', source.DOCUMENT_SCRIPT_GUID, doc('fixture-global', 'Global fixture')))
    metadata(global_path, 'b' * 32)
    write(source.LIBRARY_PATH, asset('DevsRealmDocumentLibraryAsset', source.LIBRARY_SCRIPT_GUID,
        '  m_Categories:\n  - m_Category: 0\n    m_DisplayOrder: 1\n    m_Title: Fixture\n    m_Summary: Existing catalog\n'
        '  m_Documents:\n  - {fileID: 11400000, guid: ' + 'b' * 32 + ', type: 2}\n'))
    metadata(source.LIBRARY_PATH, 'a' * 32)
    image_path = 'Assets/Resources/UI/DevsRealm/Before.png'
    write(image_path, image_bytes())
    metadata(image_path, 'd' * 32)
    owner, bundle_guid, local_id = 'e' * 32, 'c' * 32, 4643311352111938372
    private_path = 'Assets/GameData/Builds/DeviceEditor/Device-' + owner + '.asset'
    private_id = 'device-editor-' + owner + '-' + 'f' * 32
    private = asset('InteractiveDisplayContent', '16ac4c2bcf3828841b5285ee4875a0eb',
                    '  m_Tabs:\n  - m_Label: Welcome\n    m_Document: {fileID: ' + str(local_id) + '}\n')
    private += asset('DevsRealmDocumentAsset', source.DOCUMENT_SCRIPT_GUID, doc(private_id, 'Private fixture'), local_id, False)
    write(private_path, private)
    ownership = json.dumps({'schema': 'random-realm-device-editor-v1', 'ownerId': owner,
                           'bundleGuid': bundle_guid, 'rootKey': 'scene:GlobalObjectId_fixture'}, separators=(',', ':'))
    metadata(private_path, bundle_guid, "'" + ownership + "'")
    return root


class MutableAdapter:
    def __init__(self, inventory):
        self.inventory = deepcopy(inventory)
    def read_inventory(self, workspace):
        return deepcopy(self.inventory)
    def __getattr__(self, name):
        return getattr(source, name)


class SyncChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='console-content-sync-v2-')
        self.base = Path(self.temp.name).resolve()
        self.workspace = build_fixture(self.base / 'unity')
        self.root = self.base / 'library'; self.root.mkdir()
        self.settings = self.base / 'settings.json'
        self.settings.write_text(json.dumps({'root': str(self.root)}), encoding='utf-8')
        self.library = DocumentLibraryService(self.settings)
        self.dev = DevRoomService(self.library, self.base / 'no-catalog.json')
        self.adapter = MutableAdapter(source.read_inventory(self.workspace))
        self.sync = DevRoomSyncService(self.library, self.workspace, dev_room=self.dev, source_adapter=self.adapter)
    def tearDown(self):
        self.temp.cleanup()
    def import_all(self, language='en'):
        p = self.sync.preview(str(self.root), language)
        result = self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root),
            'language': language, 'planSha256': p['planSha256'], 'expectedIndexRevision': p['indexRevision'], 'draftIds': []})
        self.assertEqual(result['status'], 'applied')
        return self.sync.status(str(self.root), language)['bindings']
    def selected(self):
        bindings = self.import_all()
        binding = next(b for b in bindings if b['scope'] == 'displayContent')
        doc = self.sync.document_state(str(self.root), binding['documentId'], 'en')['document']
        return binding, doc
    def save_edit(self, doc, body=None, language='en'):
        payload = {'expectedRoot': str(self.root), 'id': doc['id'], 'title': doc['title'],
                   'body': body or doc['body'].replace('Existing body', 'Edited body'),
                   'expectedRevision': doc['revision'], 'language': language}
        self.sync.validate_save(payload)
        self.dev.save(payload)
        return self.sync.document_state(str(self.root), doc['id'], language)['document']
    def push_payload(self, binding, doc):
        return {'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'documentId': doc['id'],
                'language': 'en', 'expectedRevision': doc['revision'], 'expectedUnityRevision': binding['lastUnityRevision'], 'draftIds': []}
    def enable_fixture_bridge(self):
        path = self.sync._bridge_path('session.json', create=True)
        path.write_bytes(_json_bytes({'schemaVersion': 2, 'enabled': True, 'editorInstanceNonce': '1' * 32,
             'projectRoot': str(self.workspace), 'expiresAt': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}))

    def test_constructor_preview_and_ordinary_documents_do_not_write(self):
        before = list(self.root.rglob('*'))
        self.sync.document_state(str(self.root), language='zh')
        self.sync.preview(str(self.root), 'en')
        self.sync.status(str(self.root), 'en')
        self.assertEqual(before, list(self.root.rglob('*')))
        self.assertFalse((self.workspace / '.codex').exists())

    def test_verified_generated_navigation_is_readable_without_guessing_authored_languages(self):
        self.import_all()
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        navigation = self.sync.document_state(str(self.root), 'overview', 'en')['document']
        self.assertEqual(navigation['title'], 'Overview')
        self.assertTrue(navigation['generatedNavigation'])
        self.assertFalse(navigation['translationMissing'])
        self.assertIn('.md)', navigation['body'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
        ordinary_id = str(uuid.uuid4())
        self.dev.save({'expectedRoot': str(self.root), 'id': ordinary_id, 'title': 'User original',
                       'body': 'User authored text', 'expectedRevision': ''})
        ordinary = self.sync.document_state(str(self.root), ordinary_id, 'en')['document']
        self.assertTrue(ordinary['translationMissing'])
        self.assertNotIn('generatedNavigation', ordinary)

    def test_real_typed_private_subasset_and_order_and_pixels(self):
        binding, doc = self.selected()
        self.assertEqual(binding['localFileId'], 4643311352111938372)
        self.assertEqual(doc['syncSource']['scope'], 'displayContent')
        self.assertEqual(len(doc['mediaSlots']), 1)
        result = self.sync.media(str(self.root), doc['id'], '0', doc['revision'], 'en')
        self.assertEqual(result['mimeType'], 'image/png')
        self.assertEqual(hashlib.sha256(Path(result['path']).read_bytes()).hexdigest(), result['sha256'])
        self.assertFalse((self.workspace / '.codex').exists())

    def test_language_edits_preserved_and_stale_preview_rejected(self):
        binding, doc = self.selected()
        preview = self.sync.preview(str(self.root), 'en')
        edited = self.save_edit(doc)
        before = self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes()
        plan = self.sync.preview(str(self.root), 'en')
        row = next(c for c in plan['changes'] if c['documentId'] == doc['id'])
        self.assertEqual(row['action'], 'preserve')
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'language': 'en',
                'planSha256': preview['planSha256'], 'expectedIndexRevision': preview['indexRevision'], 'draftIds': []})
        original = next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid'])
        original['revision'] = '2' * 64
        conflict = self.sync.preview(str(self.root), 'en')
        self.assertFalse(conflict['canImport'])
        self.assertEqual(before, self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes())
        self.assertIn('Edited body', edited['body'])

    def test_upload_is_immutable_and_content_versioned_before_push(self):
        binding, doc = self.selected()
        request = {'expectedRoot': str(self.root), 'id': doc['id'], 'language': 'en', 'expectedRevision': doc['revision'],
                   'section': 0, 'filename': 'replacement.png', 'mimeType': 'image/png', 'base64': base64.b64encode(image_bytes('red')).decode()}
        uploaded = self.sync.upload_media(request)
        self.assertFalse(uploaded['savedToDocument'])
        self.assertEqual(doc['body'], self.dev.state(str(self.root), doc['id'], 'en')['document']['body'])
        baseline = next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid'])
        parsed = source.markdown_to_document(doc['body'], baseline)
        token = uploaded['image']; parsed['sections'][0]['image'] = {k: v for k, v in token.items() if k not in {'section', 'imageCaption'}}
        new_doc = self.save_edit(doc, source.document_to_markdown(parsed, include_media=True))
        self.assertNotEqual(new_doc['revision'], doc['revision'])
        resolved = self.sync.media(str(self.root), doc['id'], 0, new_doc['revision'], 'en')
        self.assertEqual(resolved['sha256'], uploaded['sha256'])
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.media(str(self.root), doc['id'], 0, doc['revision'], 'en')
        object_path = self.root.joinpath(*media.MEDIA_PARTS, uploaded['stagingName'])
        object_path.write_bytes(image_bytes('green'))
        with self.assertRaises(ValueError):
            self.sync.media(str(self.root), doc['id'], 0, new_doc['revision'], 'en')

    def test_invalid_upload_and_image_path_and_structure_rejected(self):
        binding, doc = self.selected()
        with self.assertRaises(ValueError):
            self.sync.upload_media({'expectedRoot': str(self.root), 'id': doc['id'], 'language': 'en', 'expectedRevision': doc['revision'],
                'section': 0, 'filename': 'bad.png', 'mimeType': 'image/png', 'base64': base64.b64encode(b'<script>').decode()})
        baseline = next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid'])
        parsed = source.markdown_to_document(doc['body'], baseline)
        parsed['sections'][0]['image']['assetPath'] = '../outside.png'
        with self.assertRaises(ValueError):
            self.save_edit(doc, source.document_to_markdown(parsed, include_media=True))
        with self.assertRaises(ValueError):
            self.save_edit(doc, doc['body'].replace('section 0 -->', 'section 1 -->'))

    def test_bridge_unavailable_reserves_no_operation(self):
        binding, doc = self.selected(); doc = self.save_edit(doc)
        p = self.push_payload(binding, doc)
        with self.assertRaises(DevRoomSyncConflict) as caught:
            self.sync.push_intent(p)
        self.assertFalse(caught.exception.accepted)
        self.assertEqual(self.sync.receipt(str(self.root), p['requestId'])['status'], 'not_submitted')

    def test_stable_uuid_and_language_request_pins_and_no_resend(self):
        binding, doc = self.selected(); doc = self.save_edit(doc)
        self.enable_fixture_bridge(); p = self.push_payload(binding, doc)
        result = self.sync.push_intent(p)
        self.assertEqual(result['status'], 'pending')
        path = self.sync._bridge_path('requests', p['requestId'] + '.json')
        raw = path.read_bytes(); request = json.loads(raw)
        self.assertEqual(request['document']['localFileId'], binding['localFileId'])
        self.assertEqual(request['projectLibraryGuid'], self.adapter.inventory['library']['guid'])
        self.assertEqual(request['projectId'], self.adapter.inventory['projectId'])
        self.assertEqual(request['expectedLibrary']['kind'], 'displayContent')
        with patch.object(self.sync, '_send_request', side_effect=AssertionError('duplicate delivery')):
            self.assertEqual(self.sync.push_intent(p)['status'], 'pending')
        self.assertEqual(raw, path.read_bytes())
        changed = {**p, 'language': 'zh'}
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.push_intent(changed)
        self.assertEqual(self.sync.receipt(str(self.root), p['requestId'])['status'], 'pending')

    def test_unknown_delivery_is_not_retried(self):
        binding, doc = self.selected(); doc = self.save_edit(doc)
        self.enable_fixture_bridge(); p = self.push_payload(binding, doc)
        with patch.object(self.sync, '_send_request', side_effect=OSError('delivery uncertain')):
            with self.assertRaises(OSError):
                self.sync.push_intent(p)
        with patch.object(self.sync, '_send_request', side_effect=AssertionError('unexpected retry')):
            self.assertEqual(self.sync.push_intent(p)['status'], 'unknown')

    def test_simulated_receipt_requires_actual_source_and_complete_request(self):
        binding, doc = self.selected(); doc = self.save_edit(doc)
        self.enable_fixture_bridge(); p = self.push_payload(binding, doc); self.sync.push_intent(p)
        request = json.loads(self.sync._bridge_path('requests', p['requestId'] + '.json').read_bytes())
        actual = deepcopy(next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid']))
        actual.update(deepcopy(request['target'])); actual['revision'] = '3' * 64
        actual['expectedLibrary']['revision'] = '3' * 64
        actual['contentRevision'] = source.document_content_revision(actual)
        actual['mediaRevision'] = source.document_media_revision(actual)
        self.adapter.inventory['documents'][-1] = actual
        receipt = {k: request[k] for k in ('schemaVersion','requestId','editorInstanceNonce','projectId','projectLibraryGuid','documentId',
                   'consoleRevision','contentSha256','expectedLibrary','document')}
        receipt.update(status='applied', requestSha256=_sha(_json_bytes(request)), actual=request['target'],
            appliedContentSha256=request['contentSha256'], appliedUnityRevision=actual['revision'],
            appliedMetaRevision=actual['metaRevision'], appliedStructureRevision=actual['structureRevision'],
            appliedMediaRevision=actual['mediaRevision'], appliedLibraryRevision=actual['expectedLibrary']['revision'],
            appliedLibraryMetaRevision=actual['expectedLibrary']['metaRevision'])
        path = self.sync._bridge_path('receipts', p['requestId'] + '.json', create=True)
        receipt['requestSha256'] = '0' * 64; path.write_bytes(_json_bytes(receipt))
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.receipt(str(self.root), p['requestId'])
        receipt['requestSha256'] = _sha(_json_bytes(request)); path.write_bytes(_json_bytes(receipt))
        self.assertEqual(self.sync.receipt(str(self.root), p['requestId'])['status'], 'applied')
        self.assertEqual(self.sync.status(str(self.root), 'en')['bindings'][0]['status'], 'synced')

    def test_explicit_fixture_source_identity_and_membership(self):
        doc = self.adapter.inventory['documents'][-1]
        bound = {k: doc[k] for k in ('path','guid','localFileId','expectedLibrary')}
        inv = source.read_explicit_inventory(self.workspace, [bound])
        self.assertEqual(len(inv['documents']), 1)
        self.assertEqual(inv['projectId'], self.adapter.inventory['projectId'])
        bound['localFileId'] += 1
        with self.assertRaises(ValueError):
            source.read_explicit_inventory(self.workspace, [bound])

    def test_negative_int64_owned_document_import_save_and_push_preserve_identity(self):
        original = next(d for d in self.adapter.inventory['documents'] if d['scope'] == 'displayContent')
        asset_path = self.workspace / original['path']
        negative = -(2 ** 63)
        asset_path.write_bytes(asset_path.read_bytes().replace(str(original['localFileId']).encode(), str(negative).encode()))
        self.adapter.inventory = source.read_inventory(self.workspace)
        actual = next(d for d in self.adapter.inventory['documents'] if d['scope'] == 'displayContent')
        self.assertEqual(actual['localFileId'], negative)
        bound = {k: actual[k] for k in ('path', 'guid', 'localFileId', 'expectedLibrary')}
        explicit = source.read_explicit_inventory(self.workspace, [bound])['documents'][0]
        self.assertEqual(explicit['localFileId'], negative)
        self.assertEqual(explicit['structureRevision'], actual['structureRevision'])
        binding, doc = self.selected()
        self.assertEqual(binding['localFileId'], negative)
        identity_fields = [self.adapter.inventory['projectId'], self.adapter.inventory['library']['guid'], actual['guid'], str(negative)]
        self.assertEqual(doc['id'], str(uuid.uuid5(NAMESPACE, '\n'.join(identity_fields))))
        self.assertEqual(doc['syncSource']['localFileId'], negative)
        game_before = {str(p): p.read_bytes() for p in (self.workspace / 'Assets').rglob('*') if p.is_file()}
        result = self.sync.save_document({'expectedRoot': str(self.root), 'id': doc['id'], 'language': 'en',
             'title': doc['title'], 'body': doc['body'].replace('Existing body', 'Negative identity edited body'),
             'expectedRevision': doc['revision']})
        saved = result['document']
        self.assertEqual(saved['syncSource']['localFileId'], negative)
        self.enable_fixture_bridge(); payload = self.push_payload(binding, saved)
        self.assertEqual(self.sync.push_intent(payload)['status'], 'pending')
        request = json.loads(self.sync._bridge_path('requests', payload['requestId'] + '.json').read_bytes())
        self.assertIs(type(request['document']['localFileId']), int)
        self.assertEqual(request['document']['localFileId'], negative)
        self.assertEqual(request['document']['structureRevision'], actual['structureRevision'])
        self.assertEqual(request['documentId'], doc['id'])
        self.assertEqual(game_before, {str(p): p.read_bytes() for p in (self.workspace / 'Assets').rglob('*') if p.is_file()})

    def test_document_local_id_rejects_null_and_outside_signed_int64(self):
        original = next(d for d in self.adapter.inventory['documents'] if d['scope'] == 'displayContent')
        asset_path = self.workspace / original['path']; original_raw = asset_path.read_bytes()
        bound = {k: original[k] for k in ('path', 'guid', 'localFileId', 'expectedLibrary')}
        for invalid in (0, -(2 ** 63) - 1, 2 ** 63, True, 1.0):
            with self.subTest(localFileId=invalid):
                with self.assertRaises(source.UnityDocumentError):
                    source.read_bound_document(self.workspace, original['path'], original['guid'], invalid)
                with self.assertRaises(source.UnityDocumentError):
                    source.read_explicit_inventory(self.workspace, [{**bound, 'localFileId': invalid}])
                asset_path.write_bytes(original_raw.replace(str(original['localFileId']).encode(), str(invalid).encode()))
                with self.assertRaises(source.UnityDocumentError):
                    source.read_inventory(self.workspace)
                asset_path.write_bytes(original_raw)
        self.assertEqual(source.read_inventory(self.workspace)['documents'][-1]['localFileId'], original['localFileId'])

    def test_sync_inventory_and_saved_index_validate_signed_document_ids(self):
        binding, doc = self.selected()
        inventory = deepcopy(self.adapter.inventory)
        index_path = self.root.joinpath(*INDEX_PARTS); original_raw = index_path.read_bytes()
        index = json.loads(original_raw)
        for invalid in (0, -(2 ** 63) - 1, 2 ** 63, True, 1.0):
            with self.subTest(localFileId=invalid):
                self.adapter.inventory['documents'][-1]['localFileId'] = invalid
                with self.assertRaises(ValueError):
                    self.sync.status(str(self.root), 'en')
                self.adapter.inventory = deepcopy(inventory)
                index['bindings'][doc['id']]['localFileId'] = invalid
                index_path.write_bytes(_json_bytes(index))
                with self.assertRaises(ValueError):
                    self.sync.status(str(self.root), 'en')
                index_path.write_bytes(original_raw)
        self.assertEqual(self.sync.document_state(str(self.root), doc['id'], 'en')['document']['syncSource']['localFileId'], binding['localFileId'])

    def test_v1_media_migration_preserves_catalog_language_and_original_hash(self):
        bindings = self.import_all()
        binding = next(b for b in bindings if b['scope'] == 'globalLibrary')
        identifier = binding['documentId']
        document = self.dev._read(self.root, identifier)[0]
        original_path = self.root.joinpath(*DEV_ROOM_PARTS, identifier + '.md')
        original_raw = original_path.read_bytes()
        locale_path = self.root.joinpath(*DEV_ROOM_PARTS, '.locales', identifier + '.json')
        locale_path.unlink()
        catalog = self.base / 'catalog.json'
        english = document['body'].replace('Existing body', 'Saved English translation')
        catalog.write_bytes(_json_bytes({'version': 1, 'documents': [{'id': identifier,
             'sourceTitle': document['title'], 'sourceBodySha256': _sha(document['body'].encode()),
             'variants': {'en': {'title': document['title'], 'body': english}}}]}))
        self.dev.translations_path = catalog
        index_path = self.root.joinpath(*INDEX_PARTS)
        index = json.loads(index_path.read_bytes()); old = index['bindings'][identifier]
        baseline = old.pop('lastDocument')
        old.pop('lastLocaleRawSha256'); old.pop('lastLocalizedRevisions')
        old['lastContent'] = {'title': baseline['title'], 'summary': baseline['summary'],
                              'sections': [{k:s[k] for k in ('index','title','body')} for s in baseline['sections']]}
        old['sectionMetadata'] = [{k:s[k] for k in ('index','imageCaption')} for s in baseline['sections']]
        index['schemaVersion'] = 1; index_path.write_bytes(_json_bytes(index))
        before = self.sync.document_state(str(self.root), identifier, 'en')['document']
        self.assertEqual(before['body'], english)
        plan = self.sync.preview(str(self.root), 'zh')
        row = next(c for c in plan['changes'] if c['documentId'] == identifier)
        self.assertEqual(row['action'], 'reconcile')
        self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'language': 'zh',
            'planSha256': plan['planSha256'], 'expectedIndexRevision': plan['indexRevision'], 'draftIds': []})
        after = self.sync.document_state(str(self.root), identifier, 'en')['document']
        self.assertEqual(after['body'], english)
        self.assertEqual(before['revision'], after['revision'])
        self.assertEqual(original_raw, original_path.read_bytes())
        self.assertFalse(locale_path.exists())

    def test_changed_source_text_archives_old_translation_without_rebinding(self):
        binding, doc = self.selected()
        translated = doc['body'].replace('Existing body', '旧中文译稿保留')
        self.dev.save({'expectedRoot': str(self.root), 'id': doc['id'], 'title': doc['title'], 'body': translated,
                       'language': 'zh', 'expectedRevision': doc['textRevision']})
        locale_path = self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json')
        old_raw = locale_path.read_bytes()
        index_path = self.root.joinpath(*INDEX_PARTS)
        index = json.loads(index_path.read_bytes()); index['bindings'][doc['id']]['lastLocaleRawSha256'] = _sha(old_raw)
        index_path.write_bytes(_json_bytes(index))
        game_doc = self.adapter.inventory['documents'][-1]
        game_doc['sections'][0]['body'] = 'New game source text'
        game_doc['revision'] = '5' * 64; game_doc['expectedLibrary']['revision'] = '5' * 64
        game_doc['contentRevision'] = source.document_content_revision(game_doc)
        plan = self.sync.preview(str(self.root), 'en')
        self.assertTrue(plan['canImport'])
        self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'language': 'en',
            'planSha256': plan['planSha256'], 'expectedIndexRevision': plan['indexRevision'], 'draftIds': []})
        english = self.sync.document_state(str(self.root), doc['id'], 'en')['document']
        chinese = self.sync.document_state(str(self.root), doc['id'], 'zh')['document']
        self.assertIn('New game source text', english['body'])
        self.assertTrue(chinese['translationMissing'])
        self.assertTrue(chinese['translationStale'])
        history = self.root.joinpath(*DEV_ROOM_PARTS, '.history', doc['id'], 'locales', _sha(old_raw) + '.json')
        self.assertEqual(old_raw, history.read_bytes())

    def test_failed_source_replace_rolls_back_only_own_locale(self):
        binding, doc = self.selected()
        source_before = self.root.joinpath(*DEV_ROOM_PARTS, doc['id'] + '.md').read_bytes()
        locale_before = self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes()
        game_doc = self.adapter.inventory['documents'][-1]
        game_doc['sections'][0]['body'] = 'Changed game source'
        game_doc['revision'] = '6' * 64; game_doc['expectedLibrary']['revision'] = '6' * 64
        plan = self.sync.preview(str(self.root), 'en')
        original = self.dev._atomic_write
        def fail_source(root, parts, content, before_replace=None):
            if parts == (*DEV_ROOM_PARTS, doc['id'] + '.md'):
                raise OSError('fixture failed source replace')
            return original(root, parts, content, before_replace)
        with patch.object(self.dev, '_atomic_write', side_effect=fail_source):
            with self.assertRaises(OSError):
                self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'language': 'en',
                    'planSha256': plan['planSha256'], 'expectedIndexRevision': plan['indexRevision'], 'draftIds': []})
        self.assertEqual(source_before, self.root.joinpath(*DEV_ROOM_PARTS, doc['id'] + '.md').read_bytes())
        self.assertEqual(locale_before, self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes())

    def test_fresh_import_prefers_verified_catalog_language(self):
        game_doc = next(d for d in self.adapter.inventory['documents'] if d['scope'] == 'globalLibrary')
        identifier = self.sync._document_id(self.adapter.inventory, game_doc)
        plain = source.document_to_markdown(game_doc)
        translated = plain.replace('Existing body', 'Verified English catalog body')
        catalog = self.base / 'fresh-catalog.json'
        catalog.write_bytes(_json_bytes({'version': 1, 'documents': [{'id': identifier,
             'sourceTitle': game_doc['title'], 'sourceBodySha256': _sha(plain.encode()),
             'variants': {'en': {'title': game_doc['title'], 'body': translated}}}]}))
        self.dev.translations_path = catalog
        self.import_all('en')
        current = self.sync.document_state(str(self.root), identifier, 'en')['document']
        self.assertIn('Verified English catalog body', current['body'])
        self.assertNotIn('Existing body', current['body'])
        self.assertFalse(current['translationMissing'])

    def test_media_only_source_change_changes_view_revision_without_locale_rewrite(self):
        binding, doc = self.selected()
        original_source = self.root.joinpath(*DEV_ROOM_PARTS, doc['id'] + '.md').read_bytes()
        original_locale = self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes()
        game_doc = self.adapter.inventory['documents'][-1]
        picture = game_doc['sections'][0]['image']
        replacement = image_bytes('purple'); (self.workspace / picture['assetPath']).write_bytes(replacement)
        picture['sha256'] = _sha(replacement)
        game_doc['mediaRevision'] = source.document_media_revision(game_doc)
        game_doc['contentRevision'] = source.document_content_revision(game_doc)
        plan = self.sync.preview(str(self.root), 'en')
        self.sync.import_documents({'requestId': str(uuid.uuid4()), 'expectedRoot': str(self.root), 'language': 'en',
            'planSha256': plan['planSha256'], 'expectedIndexRevision': plan['indexRevision'], 'draftIds': []})
        current = self.sync.document_state(str(self.root), doc['id'], 'en')['document']
        self.assertEqual(doc['textRevision'], current['textRevision'])
        self.assertNotEqual(doc['revision'], current['revision'])
        self.assertEqual(original_source, self.root.joinpath(*DEV_ROOM_PARTS, doc['id'] + '.md').read_bytes())
        self.assertEqual(original_locale, self.root.joinpath(*DEV_ROOM_PARTS, '.locales', doc['id'] + '.json').read_bytes())
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.media(str(self.root), doc['id'], 0, doc['revision'], 'en')
        self.assertEqual(self.sync.media(str(self.root), doc['id'], 0, current['revision'], 'en')['sha256'], picture['sha256'])

    def upload_draft(self, doc):
        return self.sync.upload_media({'expectedRoot': str(self.root), 'id': doc['id'], 'language': 'en',
            'expectedRevision': doc['revision'], 'section': 0, 'filename': 'restored.png', 'mimeType': 'image/png',
            'base64': base64.b64encode(image_bytes('orange')).decode()})

    def test_reloaded_draft_media_reads_registered_unsaved_object_without_writes(self):
        binding, doc = self.selected(); uploaded = self.upload_draft(doc)
        reloaded = DevRoomSyncService(self.library, self.workspace, dev_room=self.dev, source_adapter=self.adapter)
        before = {str(p.relative_to(self.root)): (_sha(p.read_bytes()), p.stat().st_mtime_ns)
                  for p in self.root.rglob('*') if p.is_file()}
        with patch.object(reloaded, '_write_json', side_effect=AssertionError('draft read wrote storage')):
            result = reloaded.draft_media(str(self.root), doc['id'], '0', doc['revision'], uploaded['stagingName'], 'en')
        after = {str(p.relative_to(self.root)): (_sha(p.read_bytes()), p.stat().st_mtime_ns)
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result['sha256'], uploaded['sha256'])
        self.assertEqual(result['mimeType'], 'image/png')
        self.assertEqual(_sha(Path(result['path']).read_bytes()), uploaded['sha256'])
        self.assertEqual(doc['body'], self.dev.state(str(self.root), doc['id'], 'en')['document']['body'])
        self.assertFalse((self.workspace / '.codex').exists())

    def test_draft_media_rejects_wrong_revision_root_slot_language_document_and_name(self):
        binding, doc = self.selected(); uploaded = self.upload_draft(doc)
        name = uploaded['stagingName']
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.draft_media(str(self.root), doc['id'], 0, '0' * 64, name, 'en')
        with self.assertRaises(ValueError):
            self.sync.draft_media(str(self.base), doc['id'], 0, doc['revision'], name, 'en')
        for bad_section, bad_name in ((1, name), (0, '../' + name), (0, '0' * 64 + '.png')):
            with self.assertRaises(ValueError):
                self.sync.draft_media(str(self.root), doc['id'], bad_section, doc['revision'], bad_name, 'en')
        chinese = self.sync.document_state(str(self.root), doc['id'], 'zh')['document']
        with self.assertRaises(ValueError):
            self.sync.draft_media(str(self.root), doc['id'], 0, chinese['revision'], name, 'zh')
        other = next(b for b in self.sync.status(str(self.root), 'en')['bindings'] if b['documentId'] != doc['id'])
        other_doc = self.sync.document_state(str(self.root), other['documentId'], 'en')['document']
        with self.assertRaises(ValueError):
            self.sync.draft_media(str(self.root), other_doc['id'], 0, other_doc['revision'], name, 'en')

    def test_draft_media_checks_real_pixels_hash_and_current_saved_revision(self):
        binding, doc = self.selected(); uploaded = self.upload_draft(doc); name = uploaded['stagingName']
        current = self.save_edit(doc)
        with self.assertRaises(DevRoomSyncConflict):
            self.sync.draft_media(str(self.root), doc['id'], 0, doc['revision'], name, 'en')
        result = self.sync.draft_media(str(self.root), doc['id'], 0, current['revision'], name, 'en')
        self.assertEqual(result['sha256'], uploaded['sha256'])
        Path(result['path']).write_bytes(b'<script>not pixels</script>')
        with self.assertRaises(ValueError):
            self.sync.draft_media(str(self.root), doc['id'], 0, current['revision'], name, 'en')

    def test_staged_final_path_matches_bridge_and_legacy_empty_token_normalizes(self):
        binding, doc = self.selected(); uploaded = self.upload_draft(doc)
        final_path = 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + uploaded['stagingName']
        self.assertEqual(uploaded['image']['assetPath'], final_path)
        baseline = next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid'])
        parsed = source.markdown_to_document(doc['body'], baseline)
        old_image = {k:v for k,v in uploaded['image'].items() if k not in {'section','imageCaption'}}
        old_image['assetPath'] = ''
        parsed['sections'][0]['image'] = old_image
        legacy_body = source.document_to_markdown(parsed, include_media=True)
        normalized = source.markdown_to_document(legacy_body, baseline)
        self.assertEqual(normalized['sections'][0]['image']['assetPath'], final_path)
        saved = self.save_edit(doc, legacy_body)
        self.assertEqual(saved['body'], legacy_body)
        self.enable_fixture_bridge(); payload = self.push_payload(binding, saved)
        self.sync.push_intent(payload)
        request = json.loads(self.sync._bridge_path('requests', payload['requestId'] + '.json').read_bytes())
        self.assertEqual(request['target']['sections'][0]['image']['assetPath'], final_path)
        cs = Path(__file__).resolve().parents[1].joinpath('unity','Editor','DevRoomConsoleBridge.cs').read_text(encoding='utf-8-sig')
        self.assertIn('Need(image.assetPath == path && image.resourcePath ==', cs)
        evil = deepcopy(uploaded['image']); evil['assetPath'] = 'Assets/unconfirmed.png'
        with self.assertRaises(ValueError):
            source.validate_image_edit(evil, baseline['sections'][0])

    def test_managed_navigation_summary_stays_localized_from_other_selected_document(self):
        bindings = self.import_all()
        selected = next(b for b in bindings if b['scope'] == 'displayContent')
        result = self.sync.document_state(str(self.root), selected['documentId'], 'en')
        navigation = next(d for d in result['documents'] if d['id'] == 'overview')
        self.assertEqual(navigation['title'], 'Overview')
        self.assertFalse(navigation['translationMissing'])
        self.assertTrue(navigation['generatedNavigation'])
        old = self.dev.state(str(self.root), 'overview')['document']
        self.dev.save({'expectedRoot': str(self.root), 'id': 'overview', 'title': 'Authored overview',
                       'body': 'User authored overview', 'expectedRevision': old['revision']})
        result = self.sync.document_state(str(self.root), selected['documentId'], 'en')
        navigation = next(d for d in result['documents'] if d['id'] == 'overview')
        self.assertTrue(navigation['translationMissing'])
        self.assertNotIn('generatedNavigation', navigation)

    def resource_only_fixture(self, *, all_resource_only=False):
        inventory = source.read_inventory(self.workspace)
        targets = inventory['documents'] if all_resource_only else inventory['documents'][-1:]
        pointer = 'm_Image: {fileID: 2800000, guid: ' + 'd' * 32 + ', type: 3}'
        for doc in targets:
            path = self.workspace / doc['path']
            path.write_text(path.read_text(encoding='utf-8').replace(pointer, 'm_Image: {fileID: 0}'), encoding='utf-8')
        meta = self.workspace / 'Assets/Resources/UI/DevsRealm/Before.png.meta'
        meta.write_text('fileFormatVersion: 2\nguid: ' + 'd' * 32 + '\nTextureImporter:\n  internalIDToNameTable: []\n', encoding='utf-8')
        return source.read_inventory(self.workspace)

    def test_resource_only_image_uses_unique_typed_texture_identity(self):
        inventory = self.resource_only_fixture()
        direct, fallback = inventory['documents'][0], inventory['documents'][-1]
        self.assertTrue(fallback['writebackSupported'])
        self.assertEqual(fallback['sections'][0]['image']['guid'], 'd' * 32)
        self.assertEqual(fallback['sections'][0]['image']['fileID'], direct['sections'][0]['image']['fileID'])
        self.assertEqual(fallback['sections'][0]['image']['type'], 3)
        self.assertEqual(fallback['mediaRevision'], direct['mediaRevision'])
        self.assertEqual(fallback['sections'][0]['image']['metaRevision'], direct['sections'][0]['image']['metaRevision'])

    def test_unknown_resource_texture_local_id_remains_browsable_and_blocks_push(self):
        self.adapter.inventory = self.resource_only_fixture(all_resource_only=True)
        binding, doc = self.selected()
        actual = self.adapter.inventory['documents'][-1]
        self.assertFalse(actual['writebackSupported'])
        self.assertFalse(actual['sections'][0]['image']['identityResolved'])
        self.assertEqual(actual['sections'][0]['image']['fileID'], 0)
        self.assertEqual(self.sync.media(str(self.root), doc['id'], 0, doc['revision'], 'en')['mimeType'], 'image/png')
        self.assertFalse(doc['syncSource']['writebackSupported'])
        payload = self.push_payload(binding, doc)
        with self.assertRaises(DevRoomSyncConflict) as caught:
            self.sync.push_intent(payload)
        self.assertEqual(caught.exception.code, 'unsupported_image_identity')
        self.assertFalse(caught.exception.accepted)
        self.assertEqual(self.sync.receipt(str(self.root), payload['requestId'])['status'], 'not_submitted')

    def simulated_applied(self, binding, payload):
        request = json.loads(self.sync._bridge_path('requests', payload['requestId'] + '.json').read_bytes())
        actual = deepcopy(next(d for d in self.adapter.inventory['documents'] if d['guid'] == binding['unityGuid']))
        actual.update(deepcopy(request['target'])); actual['revision'] = '7' * 64
        actual['expectedLibrary']['revision'] = '7' * 64
        actual['contentRevision'] = source.document_content_revision(actual)
        actual['mediaRevision'] = source.document_media_revision(actual)
        self.adapter.inventory['documents'][-1] = actual
        receipt = {k:request[k] for k in ('schemaVersion','requestId','editorInstanceNonce','projectId','projectLibraryGuid',
                                        'documentId','consoleRevision','contentSha256','expectedLibrary','document')}
        receipt.update(status='applied', requestSha256=_sha(_json_bytes(request)), actual=request['target'],
            appliedContentSha256=request['contentSha256'], appliedUnityRevision=actual['revision'],
            appliedMetaRevision=actual['metaRevision'], appliedStructureRevision=actual['structureRevision'],
            appliedMediaRevision=actual['mediaRevision'], appliedLibraryRevision=actual['expectedLibrary']['revision'],
            appliedLibraryMetaRevision=actual['expectedLibrary']['metaRevision'])
        self.sync._bridge_path('receipts', payload['requestId'] + '.json', create=True).write_bytes(_json_bytes(receipt))
        return request

    def chinese_catalog(self, doc):
        current = self.dev._read(self.root, doc['id'])[0]
        catalog = self.base / 'receipt-catalog.json'
        catalog.write_bytes(_json_bytes({'version':1,'documents':[{'id':doc['id'],'sourceTitle':current['title'],
            'sourceBodySha256':_sha(current['body'].encode()), 'variants':{'zh':{'title':current['title'],
            'body':current['body'].replace('Existing body','旧中文目录译文')}}}]}))
        self.dev.translations_path = catalog

    def test_applied_en_push_expires_other_variant_and_catalog_without_changing_canonical(self):
        binding, doc = self.selected()
        self.dev.save({'expectedRoot':str(self.root),'id':doc['id'],'language':'zh','title':doc['title'],
            'body':doc['body'].replace('Existing body','旧中文本地译稿'),'expectedRevision':doc['textRevision']})
        self.chinese_catalog(doc)
        doc = self.save_edit(self.sync.document_state(str(self.root),doc['id'],'en')['document'])
        locale_path = self.root.joinpath(*DEV_ROOM_PARTS,'.locales',doc['id']+'.json')
        old_raw = locale_path.read_bytes()
        canonical = self.root.joinpath(*DEV_ROOM_PARTS,doc['id']+'.md').read_bytes()
        self.enable_fixture_bridge(); payload = self.push_payload(binding,doc)
        self.sync.push_intent(payload); self.simulated_applied(binding,payload)
        result = self.sync.receipt(str(self.root),payload['requestId'])
        self.assertEqual(result['status'],'applied'); self.assertFalse(result['localChangedSincePush'])
        self.assertEqual(result['staleLanguages'],['zh'])
        english = self.sync.document_state(str(self.root),doc['id'],'en')['document']
        chinese = self.sync.document_state(str(self.root),doc['id'],'zh')['document']
        self.assertEqual(english['body'],doc['body']); self.assertFalse(english['translationMissing'])
        self.assertTrue(chinese['translationMissing']); self.assertTrue(chinese['translationStale'])
        self.assertEqual(canonical,self.root.joinpath(*DEV_ROOM_PARTS,doc['id']+'.md').read_bytes())
        stored = json.loads(locale_path.read_bytes())
        self.assertIn('旧中文本地译稿',stored['variants']['zh']['body'])
        self.assertEqual(old_raw,self.root.joinpath(*DEV_ROOM_PARTS,'.history',doc['id'],'locales',_sha(old_raw)+'.json').read_bytes())

    def test_same_content_noop_does_not_expire_other_language(self):
        binding, doc = self.selected()
        self.chinese_catalog(doc)
        doc = self.sync.document_state(str(self.root),doc['id'],'en')['document']
        locale_path = self.root.joinpath(*DEV_ROOM_PARTS,'.locales',doc['id']+'.json')
        old_raw = locale_path.read_bytes()
        result = self.sync.push_intent(self.push_payload(binding,doc))
        self.assertEqual(result['status'],'unchanged')
        self.assertEqual(old_raw,locale_path.read_bytes())
        chinese = self.sync.document_state(str(self.root),doc['id'],'zh')['document']
        self.assertFalse(chinese['translationMissing']); self.assertIn('旧中文目录译文',chinese['body'])

    def test_pending_new_en_draft_is_preserved_and_not_reported_written(self):
        binding, doc = self.selected(); self.chinese_catalog(doc)
        doc = self.save_edit(self.sync.document_state(str(self.root),doc['id'],'en')['document'])
        self.enable_fixture_bridge(); payload = self.push_payload(binding,doc); self.sync.push_intent(payload)
        latest = self.save_edit(doc,doc['body'].replace('Edited body','A newer unsent English draft'))
        self.simulated_applied(binding,payload)
        result = self.sync.receipt(str(self.root),payload['requestId'])
        self.assertEqual(result['status'],'applied'); self.assertTrue(result['localChangedSincePush'])
        current = self.sync.document_state(str(self.root),doc['id'],'en')['document']
        self.assertEqual(current['body'],latest['body'])
        actual = self.adapter.inventory['documents'][-1]
        self.assertEqual(actual['sections'][0]['body'],'Edited body')
        self.assertEqual(next(b for b in self.sync.status(str(self.root),'en')['bindings'] if b['documentId']==doc['id'])['status'],'console_changed')
        self.assertTrue(self.sync.document_state(str(self.root),doc['id'],'zh')['document']['translationStale'])

    def test_locale_index_commit_failure_stays_unknown_and_recovery_never_resends(self):
        binding, doc = self.selected(); self.chinese_catalog(doc)
        doc = self.save_edit(self.sync.document_state(str(self.root),doc['id'],'en')['document'])
        self.enable_fixture_bridge(); payload = self.push_payload(binding,doc); self.sync.push_intent(payload)
        self.simulated_applied(binding,payload)
        original_write = self.sync._write_json
        def fail_index(root,parts,value,**kwargs):
            if parts == INDEX_PARTS:
                raise OSError('fixture index commit failure after locale expiry')
            return original_write(root,parts,value,**kwargs)
        with patch.object(self.sync,'_write_json',side_effect=fail_index):
            with self.assertRaises(OSError):
                self.sync.receipt(str(self.root),payload['requestId'])
        operation = self.sync._operation(self.root,payload['requestId'])
        self.assertEqual(operation['status'],'unknown')
        self.assertIn('localeExpiry',operation)
        with patch.object(self.sync,'_send_request',side_effect=AssertionError('receipt recovery resent')):
            recovered = self.sync.receipt(str(self.root),payload['requestId'])
        self.assertEqual(recovered['status'],'applied'); self.assertFalse(recovered['localChangedSincePush'])
        self.assertTrue(self.sync.document_state(str(self.root),doc['id'],'zh')['document']['translationStale'])

    def test_status_language_truth_after_receipt_and_new_en_draft(self):
        binding, doc = self.selected(); self.chinese_catalog(doc)
        doc = self.save_edit(self.sync.document_state(str(self.root),doc['id'],'en')['document'])
        self.enable_fixture_bridge(); payload = self.push_payload(binding,doc); self.sync.push_intent(payload)
        newer = self.save_edit(doc,doc['body'].replace('Edited body','Latest unsent EN body'))
        self.simulated_applied(binding,payload); self.sync.receipt(str(self.root),payload['requestId'])
        zh = next(b for b in self.sync.status(str(self.root),'zh')['bindings'] if b['documentId']==doc['id'])
        en = next(b for b in self.sync.status(str(self.root),'en')['bindings'] if b['documentId']==doc['id'])
        self.assertEqual(zh['status'],'translation_stale'); self.assertTrue(zh['translationStale']); self.assertTrue(zh['translationMissing'])
        self.assertEqual(en['status'],'console_changed'); self.assertFalse(en['translationStale']); self.assertFalse(en['translationMissing'])
        self.assertEqual(self.sync.document_state(str(self.root),doc['id'],'en')['document']['body'],newer['body'])
        missing = next(b for b in self.sync.status(str(self.root),'zh')['bindings'] if b['documentId']!=doc['id'])
        self.assertEqual(missing['status'],'translation_missing')
        navigation = next(d for d in self.sync.document_state(str(self.root),doc['id'],'en')['documents'] if d['id']=='overview')
        self.assertFalse(navigation['translationMissing']); self.assertTrue(navigation['generatedNavigation'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-workspace')
    args, rest = parser.parse_known_args()
    if args.inventory_workspace:
        inventory = source.read_inventory(args.inventory_workspace)
        print(json.dumps({'workspace': inventory['workspace'], 'documentCount': len(inventory['documents']),
              'sectionCount': sum(len(d['sections']) for d in inventory['documents']),
              'images': [{'documentId': d['id'], 'localFileId': d['localFileId'], 'section': s['index'], **s['image']}
                         for d in inventory['documents'] for s in d['sections'] if s['image']['sha256']]}, ensure_ascii=False))
    else:
        unittest.main(argv=[sys.argv[0], *rest])
