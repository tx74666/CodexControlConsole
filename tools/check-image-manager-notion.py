"""Isolated synchronization checks. No account, network, or user library used."""
import hashlib
import html
import io
import json
from pathlib import Path
import sys
import tempfile
import re
import unittest
from unittest.mock import patch
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, parse_qs, urlsplit

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_manager import ImageManagerService
import image_manager_notion as notion_module
from image_manager_notion import (ImageManagerNotion, CodexNotionRPC, NotionSyncError,
    _acquire_file_lock, _release_file_lock, _catalog_bytes, _entry, _reference_name,
    _catalog_identity, _same_catalog_name, CATALOG_PREFIX)

PAGE = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def png(color):
    stream = io.BytesIO()
    Image.new('RGB', (7, 5), color).save(stream, format='PNG')
    return stream.getvalue()


class FakeRemote:
    def __init__(self, page_mode=False):
        self.originals, self.uploads, self.calls = {}, {}, []
        self.fail_upload = False
        self.before_upload = None
        self.posts = 0
        self.catalog_posts = 0
        self.fail_catalog_upload = False
        self.normalize_filenames = False
        self.exit_error = None
        self.page_mode = page_mode
        self.page_writes = 0
        self.fail_page_before_write = self.fail_page_after_write = False
        self.page_text = ('User notes before\n\n<synced-block url="https://app.notion.com/p/' + PAGE.replace('-','') + '#' + OTHER.replace('-','')
            + '">\n## Image\n\n<toggle>\n同步记录\n\n' + notion_module.GALLERY_MARKER + '\n</toggle>\n</synced-block>\n\nUser notes after')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.exit_error is not None:
            raise self.exit_error

    def call(self, action, arguments):
        self.calls.append((action, arguments))
        if action == 'fetch':
            return {'id': PAGE, 'metadata': {'type': 'page' if self.page_mode else 'folder'},
                'text': self.page_text if self.page_mode else '\n'.join('<image source="' + ref + '" />' for ref in self.originals)}
        if action == 'prepare':
            identifier = str(uuid.uuid4())
            self.uploads[identifier] = {'name': arguments['filename']}
            if self.before_upload:
                self.before_upload()
            return {'file_upload_id': identifier, 'filename': arguments['filename'],
                'upload_headers': {'Authorization': 'Bearer SECRET_SHOULD_NEVER_BE_SAVED'}}
        if action == 'attach':
            for identifier in arguments['file_upload_ids']:
                item = self.uploads[identifier]
                name = item['name'].replace(' ', '_') if self.normalize_filenames else item['name']
                reference = 'notion-file-block://' + PAGE + '/' + identifier + '?name=' + quote(name)
                self.originals[reference] = item['data']
            return {'ok': True}
        if action == 'download':
            return {'files': [{'url': reference} for reference in arguments['references']]}
        if action == 'page':
            self.page_writes += 1
            if self.fail_page_before_write:
                raise NotionSyncError('test_page_unknown', '页面写入回执未知。', unknown=True)
            assert arguments['page_id'] == PAGE and arguments['command'] == 'update_content'
            update = arguments['content_updates'][0]
            assert self.page_text.count(update['old_str']) == 1
            def save_source(match):
                source = html.unescape(match[2])
                if source.startswith('file-upload://'):
                    identifier = notion_module._source_id(source)
                    item = self.uploads[identifier]
                    name, data = item['name'], item['data']
                else:
                    identifier = notion_module._source_id(source)
                    name, data = _reference_name(source), self.originals[source]
                if self.normalize_filenames:
                    name = name.replace(' ', '_')
                # Notion copies an existing file into a new block. Its upload
                # identity is stable even though the first block UUID changes.
                reference = 'notion-file-block://' + str(uuid.uuid4()) + '/' + identifier + '?name=' + quote(name)
                self.originals[reference] = data
                return match[1] + reference + match[3]
            replacement = re.sub(r'(<(?:image|file)\s+source=")([^"<>]+)(")', save_source, update['new_str'])
            self.page_text = self.page_text.replace(update['old_str'], replacement, 1)
            if self.fail_page_after_write:
                raise NotionSyncError('test_page_unknown', '页面写入回执未知。', unknown=True)
            return {'ok': True}
        raise AssertionError(action)

    def authorize_upload(self, uploaded):
        return notion_module._upload_source(uploaded)

    def upload(self, request, path):
        is_catalog = request['filename'].startswith(CATALOG_PREFIX)
        if is_catalog:
            self.catalog_posts += 1
        else:
            self.posts += 1
        if self.fail_upload or (is_catalog and self.fail_catalog_upload):
            raise NotionSyncError('test_network_unknown', '传输回执未知。', unknown=True)
        identifier = request['file_upload_id']
        self.uploads[identifier]['data'] = Path(path).read_bytes()
        return {'id': identifier, 'status': 'uploaded', 'markdown_source':'file-upload://' + identifier}

    def download(self, reference):
        return self.originals[reference]

    def add_catalog(self, entries=None, *, data=None, when=None):
        data = _catalog_bytes(entries) if data is None else data
        digest = hashlib.sha256(data).hexdigest()
        when = when or datetime.now(timezone.utc)
        name = CATALOG_PREFIX + when.strftime('%Y%m%dT%H%M%S%fZ') + '-' + digest + '.json'
        name = name.replace(' ', '_') if self.normalize_filenames else name
        reference = 'notion-file-block://' + PAGE + '/' + str(uuid.uuid4()) + '?name=' + quote(name)
        self.originals[reference] = data
        if self.page_mode:
            self.page_text = self.page_text.replace('</toggle>', '<file source="' + reference + '">\n方案目录\n</file>\n</toggle>', 1)
        return reference

    def latest_catalog(self):
        refs = [reference for reference in self.originals if _catalog_identity(_reference_name(reference))]
        return json.loads(self.originals[max(refs, key=lambda ref:_catalog_identity(_reference_name(ref)))])

    def add_image(self, name, data, caption='Existing image'):
        reference = 'notion-file-block://' + PAGE + '/' + str(uuid.uuid4()) + '?name=' + quote(name)
        self.originals[reference] = data
        if self.page_mode:
            self.page_text = self.page_text.replace('<toggle>', '<image source="' + reference + '">\n' + caption + '\n</image>\n\n<toggle>', 1)
        return reference


class Checks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-image-notion-')
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / 'library'
        self.root.mkdir()
        self.data = png('red')
        (self.root / 'Sample.png').write_bytes(self.data)
        self.service = ImageManagerService(self.directory / 'config.json')
        self.service.configure({'root': str(self.root), 'notionPage': PAGE})
        self.service.scan({'expectedRoot': str(self.root)})
        self.remote = FakeRemote()
        self.provider = ImageManagerNotion(self.service, self.directory / 'private',
            rpc_factory=lambda root, page: self.remote, transfer_factory=lambda: self.remote)

    def tearDown(self):
        self.provider.wait(5)
        self.assertEqual(self.root.parent, self.directory)
        self.temporary.cleanup()

    def sync(self, source='local', target='notion', request='first'):
        self.provider.sync({'source': source, 'target': target, 'expectedRoot': str(self.root), 'requestId': request})
        result = self.provider.wait(5)
        self.assertFalse(self.provider.worker.is_alive())
        return result

    def test_upload_original_verify_and_repeat_without_upload(self):
        result = self.sync()
        self.assertEqual(result['operation']['status'], 'completed')
        self.assertTrue(result['notion']['verified'])
        self.assertEqual(self.remote.posts, 1)
        self.assertEqual(next(iter(self.remote.originals.values())), self.data)
        self.assertEqual((self.root / 'Sample.png').read_bytes(), self.data)
        self.assertEqual(next(iter(self.remote.uploads.values()))['name'], 'Sample - 7x5.png')
        self.sync(request='second')
        self.assertEqual(self.remote.posts, 1)
        for path in (self.directory / 'private').glob('*.json'):
            text = path.read_text(encoding='utf8')
            self.assertNotIn('SECRET_SHOULD_NEVER_BE_SAVED', text)
            self.assertNotIn('upload_headers', text)
        self.assertEqual(self.provider.operation('second')['operation']['requestId'], 'second')

    def test_native_page_upload_and_repeat_preserve_outside_content_and_original_bytes(self):
        self.remote = FakeRemote(page_mode=True)
        before = self.remote.page_text
        result = self.sync()
        self.assertEqual(result['operation']['status'], 'completed', result['operation'])
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (1,1,2))
        entity = self.remote.call('fetch', {'id':PAGE})
        images = notion_module._image_refs(entity)
        self.assertEqual(len(images), 1)
        self.assertEqual(self.remote.originals[images[0]], self.data)
        self.assertIn('Sample · 方案1 · 7×5', self.remote.page_text)
        self.assertTrue(self.remote.page_text.startswith('User notes before\n\n'))
        self.assertTrue(self.remote.page_text.endswith('\n\nUser notes after'))
        self.assertNotEqual(before, self.remote.page_text)
        writes = self.remote.page_writes
        result = self.sync(request='page-repeat')
        self.assertEqual(result['operation']['status'], 'completed')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (1,1,writes))

    def test_native_page_metadata_only_refreshes_caption_and_keeps_catalog_history(self):
        self.remote = FakeRemote(page_mode=True)
        item = self.service.state()['items'][0]
        self.remote.add_image('Sample - 7x5.png', self.data, 'Sample · 方案1 · 7×5')
        self.remote.add_catalog({item['sha256']:_entry(item)})
        self.assertEqual(self.sync()['operation']['status'], 'completed')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (0,0,0))
        self.service.annotate({'expectedRoot':str(self.root), 'path':item['path'], 'sha256':item['sha256'],
            'groupTitle':'主游戏 · 图标', 'variantLabel':'第二方案'})
        result = self.sync(request='page-label-update')
        self.assertEqual(result['operation']['status'], 'completed', result['operation'])
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (0,1,1))
        self.assertIn('主游戏 · 图标 · 第二方案 · 7×5', self.remote.page_text)
        entity = self.remote.call('fetch', {'id':PAGE})
        self.assertEqual(len(notion_module._image_refs(entity)), 1)
        self.assertEqual(len([ref for ref in self.provider._refs(entity) if _catalog_identity(_reference_name(ref))]), 2)
        self.assertTrue(self.remote.page_text.endswith('\n\nUser notes after'))

    def test_native_page_unknown_before_or_after_write_never_reposts_same_request(self):
        for after in (False, True):
            with self.subTest(after=after):
                self.remote = FakeRemote(page_mode=True)
                self.remote.fail_page_after_write = after
                self.remote.fail_page_before_write = not after
                # Use a separate page receipt ledger for each isolated scenario.
                self.provider = ImageManagerNotion(self.service, self.directory / ('page-private-'+str(after)),
                    rpc_factory=lambda root,page:self.remote, transfer_factory=lambda:self.remote)
                result = self.sync(request='page-unknown')
                self.assertEqual(result['operation']['status'], 'unknown')
                writes = (self.remote.posts,self.remote.catalog_posts,self.remote.page_writes)
                self.sync(request='page-unknown')
                self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), writes)
                self.assertEqual(writes, (1,0,1))
                if not after:
                    self.sync(request='page-new-intent')
                    self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), writes)
                self.assertTrue(self.remote.page_text.endswith('\n\nUser notes after'))

    def test_native_page_owned_region_change_stops_before_update(self):
        self.remote = FakeRemote(page_mode=True)
        original = self.provider._page_rows
        def concurrent_edit(*args):
            result = original(*args)
            self.remote.page_text = self.remote.page_text.replace('## Image', '## User gallery edit')
            return result
        with patch.object(self.provider, '_page_rows', side_effect=concurrent_edit):
            result = self.sync()
        self.assertEqual(result['operation']['status'], 'failed')
        self.assertEqual(result['operation']['code'], 'notion_gallery_changed')
        self.assertEqual(self.remote.page_writes, 0)
        self.assertIn('## User gallery edit', self.remote.page_text)

    def test_native_page_read_only_completion_rechecks_new_blocks_without_new_upload_or_page_write(self):
        self.remote = FakeRemote(page_mode=True)
        original_write = notion_module._atomic_json
        denied = False
        def fail_final_once(path, value):
            nonlocal denied
            if path.parent == self.provider.directory and value.get('operation',{}).get('status') == 'completed' and not denied:
                denied = True
                raise PermissionError('fixture final receipt denial')
            return original_write(path, value)
        with patch.object(notion_module, '_atomic_json', side_effect=fail_final_once):
            pending = self.sync(request='page-final-save')['operation']
        self.assertEqual((pending['status'],pending['code']), ('unknown','verified_completion_unrecorded'))
        self.assertTrue(pending['recheckable'])
        observed = set(notion_module._image_refs(self.remote.call('fetch', {'id':PAGE})))
        self.assertTrue(any(item.get('reference') not in observed for item in pending['items']))
        writes = (self.remote.posts,self.remote.catalog_posts,self.remote.page_writes)
        completed = self.sync(request='page-final-save')['operation']
        self.assertEqual(completed['status'], 'completed', completed)
        self.assertEqual(completed['id'], pending['id'])
        self.assertEqual(completed['items'], pending['items'])
        self.assertEqual(completed['verifiedOriginals'][0]['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), writes)

    def test_native_page_unchanged_catalogue_does_not_claim_stale_caption_is_synchronized(self):
        self.remote = FakeRemote(page_mode=True)
        self.assertEqual(self.sync()['operation']['status'], 'completed')
        self.remote.page_text = self.remote.page_text.replace('Sample · 方案1 · 7×5', 'Manually changed caption')
        writes = (self.remote.posts,self.remote.catalog_posts,self.remote.page_writes)
        operation = self.sync(request='page-stale-caption')['operation']
        self.assertEqual((operation['status'],operation['code']), ('failed','notion_gallery_unverified'))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), writes)

    def test_native_page_pull_reads_only_owned_gallery_and_restores_metadata_without_apply(self):
        self.remote = FakeRemote(page_mode=True)
        incoming = png('blue')
        digest = hashlib.sha256(incoming).hexdigest()
        self.remote.add_image('Incoming - 7x5.png', incoming)
        self.remote.add_catalog({digest:{'groupTitle':'Playtest · 图标','variantLabel':'设备方案','derivedFromId':''}})
        outside = self.remote.add_image('Outside - 7x5.png', png('green'))
        own = notion_module._page_region(self.remote.call('fetch', {'id':PAGE}))['text']
        self.remote.page_text = self.remote.page_text.replace('<image source="'+outside+'">\nExisting image\n</image>\n\n', '')
        self.remote.page_text += '\n<image source="'+outside+'">\nUnrelated user image\n</image>'
        result = self.sync(source='notion', target='console')
        self.assertEqual(result['operation']['status'], 'needs_review', result['operation'])
        plan = self.service.state()['plan']
        self.assertEqual(len(plan['candidates']), 1)
        item = plan['candidates'][0]['incoming']
        self.assertEqual((item['groupTitle'],item['variantLabel']), ('Playtest · 图标','设备方案'))
        self.assertEqual((self.root / item['path']).read_bytes(), incoming)
        self.assertEqual((self.root / 'Sample.png').read_bytes(), self.data)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (0,0,0))

    def test_rpc_page_scope_requires_unique_region_same_page_and_observed_sources(self):
        remote = FakeRemote(page_mode=True)
        rpc = CodexNotionRPC('unused', self.root, PAGE)
        entity = remote.call('fetch', {'id':PAGE})
        with patch.object(rpc, '_call', return_value=entity):
            rpc.call('fetch', {'id':PAGE})
        old = notion_module._page_region(entity)['text']
        valid = {'page_id':PAGE, 'command':'update_content', 'content_updates':[{'old_str':old,'new_str':old.replace('## Image','## Image gallery')}]}
        with patch.object(rpc, '_call', return_value={'ok':True}) as call:
            rpc.call('page', valid)
            self.assertEqual(call.call_count, 1)
            bad_updates = [dict(valid, page_id=OTHER), dict(valid,command='replace_content'),
                dict(valid,content_updates=[{'old_str':old,'new_str':old+'\nOutside text'}]),
                dict(valid,content_updates=[{'old_str':old,'new_str':old.replace('</toggle>', '<image source="notion-file-block://'+OTHER+'/'+OTHER+'?name=foreign.png">x</image>\n</toggle>')}])]
            for arguments in bad_updates:
                with self.assertRaises(NotionSyncError):
                    rpc.call('page', arguments)
            self.assertEqual(call.call_count, 1)
        for text in (remote.page_text.replace(notion_module.GALLERY_MARKER, 'missing'), remote.page_text+'\n'+old):
            with patch.object(rpc, '_call', return_value=dict(entity,text=text)):
                with self.assertRaises(NotionSyncError):
                    rpc.call('fetch', {'id':PAGE})
        invalid = [dict(entity,truncated=True), dict(entity,unknown_block_count=1), dict(entity,unknown_block_ids=[OTHER]),
            dict(entity,text=entity['text'].replace('/p/'+PAGE.replace('-',''), '/p/'+OTHER.replace('-',''))),
            dict(entity,text=entity['text'].replace('https://app.notion.com', 'https://foreign.example')),
            dict(entity,text=entity['text'].replace('#'+OTHER.replace('-',''), '#not-a-block'))]
        for result in invalid:
            with patch.object(rpc, '_call', return_value=result):
                with self.assertRaises(NotionSyncError):
                    rpc.call('fetch', {'id':PAGE})

    def test_native_page_caption_and_outside_uris_never_grant_attachment_scope(self):
        remote = FakeRemote(page_mode=True)
        image = remote.add_image('Visible.png', self.data)
        catalogue = remote.add_catalog({})
        foreign = 'notion-file-block://'+OTHER+'/'+OTHER+'?name=private.png'
        historical = 'notion-file-block://'+OTHER+'/'+PAGE+'?name=historical.png'
        remote.page_text = remote.page_text.replace(notion_module.GALLERY_MARKER,
            notion_module.GALLERY_MARKER+'\n\nCaption text '+foreign+'\n<file source="'+historical+'">\n历史原件\n</file>')
        remote.page_text += '\nOutside text '+foreign
        entity = remote.call('fetch', {'id':PAGE})
        self.assertEqual(notion_module._image_refs(entity), [image])
        self.assertEqual(set(notion_module._stable_refs(entity)), {image,catalogue,historical})
        rpc = CodexNotionRPC('unused', self.root, PAGE)
        with patch.object(rpc, '_call', return_value=entity):
            rpc.call('fetch', {'id':PAGE})
        self.assertNotIn(foreign, rpc.allowed_refs)
        with self.assertRaises(NotionSyncError):
            rpc.call('download', {'references':[foreign]})
        region = notion_module._page_region(entity)
        new = region['text'].replace('</toggle>', '<image source="'+foreign+'">\nFake image\n</image>\n</toggle>')
        with self.assertRaises(NotionSyncError):
            rpc.call('page', {'page_id':PAGE,'command':'update_content',
                'content_updates':[{'old_str':region['text'],'new_str':new}]})
        # Native media without captions and reordered attributes are still media.
        changed = dict(entity,text=entity['text'].replace('<image source="'+image+'">\nExisting image\n</image>',
            '<image color="gray" source="'+image+'" />'))
        self.assertEqual(notion_module._image_refs(changed), [image])

    def test_native_page_unsupported_external_source_stops_without_deleting_it(self):
        self.remote = FakeRemote(page_mode=True)
        self.remote.page_text = self.remote.page_text.replace('</toggle>',
            '<image source="https://example.invalid/existing.png">\nUser image\n</image>\n</toggle>')
        protected = self.remote.page_text
        operation = self.sync()['operation']
        self.assertEqual((operation['status'],operation['code']), ('failed','notion_gallery_source_unsupported'))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (0,0,0))
        self.assertEqual(self.remote.page_text, protected)

    def test_pending_inbox_is_not_uploaded(self):
        (self.root / 'inbox' / 'Unconfirmed.png').write_bytes(png('blue'))
        self.service.scan({'expectedRoot': str(self.root)})
        self.sync()
        self.assertEqual(self.remote.posts, 1)
        self.assertEqual(sum(not _reference_name(ref).endswith('.json') for ref in self.remote.originals), 1)
        self.assertTrue((self.root / 'inbox' / 'Unconfirmed.png').exists())

    def test_uncertain_upload_is_never_sent_again(self):
        self.remote.fail_upload = True
        self.assertEqual(self.sync()['operation']['status'], 'unknown')
        self.assertEqual(self.sync(request='second')['operation']['status'], 'unknown')
        self.assertEqual(self.remote.posts, 1)
        self.assertEqual(sum(action == 'prepare' for action, _ in self.remote.calls), 1)

    def test_changed_local_file_is_not_uploaded(self):
        (self.root / 'Sample.png').write_bytes(png('green'))
        result = self.sync()
        self.assertEqual(result['operation']['status'], 'failed')
        self.assertEqual(result['operation']['code'], 'local_original_changed')
        self.assertEqual(self.remote.posts, 0)

    def test_changed_local_file_cannot_reuse_stale_synced_index(self):
        self.sync()
        (self.root / 'Sample.png').write_bytes(png('green'))
        result = self.sync(request='changed-original')
        self.assertEqual(result['operation']['status'], 'failed')
        self.assertEqual(result['operation']['code'], 'local_original_changed')
        self.assertEqual(self.remote.posts, 1)

    def test_download_only_stages_review_and_preserves_conflict(self):
        incoming = png('blue')
        reference = 'notion-file-block://' + PAGE + '/' + OTHER + '?name=Sample.png'
        self.remote.originals[reference] = incoming
        result = self.sync(source='notion', target='all')
        self.assertEqual(result['operation']['status'], 'needs_review')
        self.assertEqual((self.root / 'Sample.png').read_bytes(), self.data)
        plan = self.service.state()['plan']
        self.assertEqual(plan['counts']['conflict'], 1)
        self.assertEqual(next((self.root / 'inbox').rglob('*.png')).read_bytes(), incoming)

    def test_same_request_returns_original_operation(self):
        first = self.sync()
        second = self.sync()
        self.assertEqual(first['operation']['id'], second['operation']['id'])
        self.assertEqual(self.remote.posts, 1)

    def test_target_changed_during_prepare_stops_before_upload(self):
        self.remote.before_upload = lambda: self.service.configure({'notionPage': OTHER})
        self.sync()
        self.assertEqual(self.remote.posts, 0)
        self.assertFalse(any(action == 'attach' for action, _ in self.remote.calls))

    def test_rpc_refuses_arbitrary_tools_pages_and_removal(self):
        rpc = CodexNotionRPC('unused', self.root, PAGE)
        for action, arguments in [('fetch', {'id': OTHER}), ('delete', {}),
                ('attach', {'folder_id': PAGE, 'command': 'remove_files', 'file_urls': ['x']}),
                ('download', {'references': ['notion-file-block://unobserved']})]:
            with self.assertRaises(NotionSyncError):
                rpc.call(action, arguments)

    def test_unverified_bridge_is_not_claimed_authenticated(self):
        state = self.provider.state()
        self.assertTrue(state['notion']['canAttempt'])
        self.assertFalse(state['notionAvailable'])
        self.assertFalse(state['notion']['verified'])

    def test_uncertain_original_is_still_blocked_after_changing_local_root(self):
        self.remote.fail_upload = True
        self.sync()
        other_root = self.directory / 'second-library'
        other_root.mkdir()
        (other_root / 'Same.png').write_bytes(self.data)
        second_service = ImageManagerService(self.directory / 'second-config.json')
        second_service.configure({'root': str(other_root), 'notionPage': PAGE})
        second_service.scan({'expectedRoot': str(other_root)})
        provider = ImageManagerNotion(second_service, self.directory / 'private',
            rpc_factory=lambda root, page: self.remote, transfer_factory=lambda: self.remote)
        provider.sync({'source': 'local', 'target': 'notion', 'expectedRoot': str(other_root), 'requestId': 'other-root'})
        result = provider.wait(5)
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertEqual(self.remote.posts, 1)

    def test_page_lock_prevents_another_instance_from_starting(self):
        held = _acquire_file_lock(self.directory / 'private' / ('target-' + PAGE + '.lock'))
        try:
            self.assertTrue(self.provider.busy)
            with self.assertRaises(NotionSyncError) as caught:
                self.provider.sync({'source': 'local', 'target': 'notion', 'expectedRoot': str(self.root)})
            self.assertEqual(caught.exception.code, 'sync_busy')
            self.assertEqual(self.remote.posts, 0)
        finally:
            _release_file_lock(held)

    def test_request_identity_cannot_change_direction(self):
        self.sync()
        with self.assertRaises(NotionSyncError):
            self.provider.sync({'source': 'notion', 'target': 'local', 'expectedRoot': str(self.root), 'requestId': 'first'})

    def annotate(self, name, label, *, group='Mark', derived=''):
        item = next(item for item in self.service.state()['items'] if item['name'] == name)
        self.service.annotate({'expectedRoot':str(self.root), 'path':item['path'], 'sha256':item['sha256'],
            'groupTitle':group, 'variantLabel':label, 'derivedFromId':derived})
        return item['sha256']

    def test_catalog_metadata_roundtrip_and_metadata_only_update(self):
        blue = png('blue')
        (self.root / 'Other.png').write_bytes(blue)
        self.service.scan({'expectedRoot':str(self.root)})
        red_sha = self.annotate('Sample.png', 'Original')
        blue_sha = self.annotate('Other.png', 'Transparent', derived=red_sha)
        result = self.sync()
        self.assertEqual(result['operation']['status'], 'completed')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (2, 1))
        names = [item['name'] for item in self.remote.uploads.values() if not item['name'].endswith('.json')]
        self.assertTrue(any('[方案 Transparent]' in name for name in names))
        entries = self.remote.latest_catalog()['entries']
        self.assertEqual(entries[blue_sha]['derivedFromId'], red_sha)
        self.assertNotIn(str(self.root), json.dumps(entries))
        self.annotate('Other.png', 'Transparent revised', derived=red_sha)
        self.sync(request='metadata-only')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (2, 2))
        self.assertEqual(self.remote.latest_catalog()['entries'][blue_sha]['variantLabel'], 'Transparent revised')
        self.assertEqual(names, [item['name'] for item in self.remote.uploads.values() if not item['name'].endswith('.json')])
        sink_root = self.directory / 'sink'
        sink_root.mkdir()
        sink = ImageManagerService(self.directory / 'sink-config.json')
        sink.configure({'root':str(sink_root), 'notionPage':PAGE})
        provider = ImageManagerNotion(sink, self.directory / 'private',
            rpc_factory=lambda root, page:self.remote, transfer_factory=lambda:self.remote)
        provider.sync({'source':'notion', 'target':'local', 'expectedRoot':str(sink_root), 'requestId':'metadata-roundtrip'})
        result = provider.wait(5)
        self.assertEqual(result['operation']['status'], 'needs_review')
        state = sink.state()
        self.assertEqual(state['items'], [])
        self.assertEqual(state['inboxCount'], 2)
        incoming = {row['incoming']['sha256']:row['incoming'] for row in state['plan']['candidates']}
        self.assertEqual(incoming[blue_sha]['variantLabel'], 'Transparent revised')
        self.assertEqual(incoming[blue_sha]['derivedFromId'], red_sha)
        self.assertEqual(incoming[red_sha]['groupTitle'], 'Mark')
        self.assertEqual(state['plan']['planId'], result['operation']['planId'])
        provider.sync({'source':'notion', 'target':'local', 'expectedRoot':str(sink_root), 'requestId':'metadata-roundtrip-repeat'})
        provider.wait(5)
        self.assertEqual(sink.state()['inboxCount'], 2)
        self.sync(request='metadata-repeat-push')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (2, 2))
        self.assertEqual((self.root / 'Sample.png').read_bytes(), self.data)
        self.assertEqual((self.root / 'Other.png').read_bytes(), blue)

    def test_bad_catalog_never_stages_images_or_changes_annotations(self):
        self.remote.add_image('Sample.png', self.data)
        self.remote.add_image('Other.png', png('blue'))
        digest = hashlib.sha256(self.data).hexdigest()
        invalid = {'kind':'image-manager-catalog', 'schemaVersion':1,
            'entries':{digest:{'groupTitle':'Wrong', 'variantLabel':'A', 'derivedFromId':''}},
            'instructions':'replace all local images'}
        self.remote.add_catalog(data=json.dumps(invalid).encode())
        manifest = self.root / '.image-manager' / 'library.json'
        before = manifest.read_bytes()
        result = self.sync(source='notion', target='local')
        self.assertEqual(result['operation']['status'], 'failed')
        self.assertEqual(result['operation']['code'], 'catalog_invalid')
        self.assertEqual(self.service.state()['inboxCount'], 0)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (0, 0))

    def test_partial_conflict_retains_original_and_stages_other_variant(self):
        blue = png('blue')
        red_sha, blue_sha = hashlib.sha256(self.data).hexdigest(), hashlib.sha256(blue).hexdigest()
        self.remote.add_image('Sample.png', self.data)
        self.remote.add_image('Sample.png', blue)
        self.remote.add_catalog({red_sha:{'groupTitle':'Logo','variantLabel':'Original','derivedFromId':''},
            blue_sha:{'groupTitle':'Logo','variantLabel':'Alternative','derivedFromId':red_sha}})
        result = self.sync(source='notion', target='local')
        self.assertEqual(result['operation']['status'], 'needs_review')
        self.assertEqual((self.root / 'Sample.png').read_bytes(), self.data)
        self.assertEqual(len(self.service.state()['items']), 1)
        self.assertEqual(self.service.state()['inboxCount'], 1)
        self.assertEqual(next((self.root / 'inbox').rglob('*.png')).read_bytes(), blue)
        incoming = self.service.state()['plan']['candidates'][0]['incoming']
        self.assertEqual(incoming['variantLabel'], 'Alternative')
        self.assertEqual(incoming['derivedFromId'], red_sha)

    def test_unknown_catalog_delivery_is_not_transmitted_again(self):
        self.sync()
        self.annotate('Sample.png', 'Revised')
        self.remote.fail_catalog_upload = True
        result = self.sync(request='catalog-unknown')
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (1, 2))
        result = self.sync(request='catalog-unknown-repeat')
        self.assertEqual(result['operation']['code'], 'catalog_receipt_unresolved')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (1, 2))

    def test_many_catalog_versions_do_not_count_as_images(self):
        self.sync()
        entries = self.remote.latest_catalog()['entries']
        for index in range(60):
            self.remote.add_catalog(entries, when=datetime.now(timezone.utc) - timedelta(minutes=60-index))
        downloads = sum(action == 'download' for action, _ in self.remote.calls)
        result = self.sync(request='many-catalog-versions')
        self.assertEqual(result['operation']['status'], 'completed')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (1, 1))
        self.assertLessEqual(sum(action == 'download' for action, _ in self.remote.calls) - downloads, 2)

    def test_missing_derived_source_is_preserved_as_pending(self):
        self.sync()
        digest = hashlib.sha256(self.data).hexdigest()
        missing = 'f'*64
        self.remote.add_catalog({digest:{'groupTitle':'Logo', 'variantLabel':'Transparent', 'derivedFromId':missing}})
        result = self.sync(source='notion', target='local', request='pending-source')
        self.assertEqual(result['operation']['status'], 'completed')
        item = self.service.state()['items'][0]
        self.assertEqual(item['derivedFromId'], '')
        self.assertEqual(item['pendingDerivedFromId'], missing)
        self.assertTrue(result['operation']['annotations']['unresolved'])
        before = self.remote.catalog_posts
        self.sync(request='pending-source-repeat')
        self.assertEqual(self.remote.catalog_posts, before)
        self.assertEqual(self.remote.latest_catalog()['entries'][digest]['derivedFromId'], missing)

    def test_push_preserves_remote_entries_outside_selected_local_assets(self):
        self.sync()
        cloud_data = png('green')
        cloud_sha = hashlib.sha256(cloud_data).hexdigest()
        self.remote.add_image('Cloud.png', cloud_data)
        entries = self.remote.latest_catalog()['entries']
        cloud_entry = {'groupTitle':'Cloud collection', 'variantLabel':'Remote choice', 'derivedFromId':''}
        entries[cloud_sha] = cloud_entry
        self.remote.add_catalog(entries)
        local_sha = self.annotate('Sample.png', 'Local choice', group='Local collection')
        result = self.sync(request='merge-remote-entries')
        self.assertEqual(result['operation']['status'], 'completed')
        merged = self.remote.latest_catalog()['entries']
        self.assertEqual(merged[cloud_sha], cloud_entry)
        self.assertEqual(merged[local_sha]['variantLabel'], 'Local choice')
        self.assertEqual((self.remote.posts, self.remote.catalog_posts), (1, 2))

    def test_catalog_cycle_is_rejected_before_staging_or_annotation(self):
        blue = png('blue')
        red_sha, blue_sha = hashlib.sha256(self.data).hexdigest(), hashlib.sha256(blue).hexdigest()
        self.remote.add_image('Sample.png', self.data)
        self.remote.add_image('Other.png', blue)
        invalid = {'kind':'image-manager-catalog', 'schemaVersion':1, 'entries':{
            red_sha:{'groupTitle':'Logo','variantLabel':'A','derivedFromId':blue_sha},
            blue_sha:{'groupTitle':'Logo','variantLabel':'B','derivedFromId':red_sha}}}
        self.remote.add_catalog(data=json.dumps(invalid).encode())
        manifest = self.root / '.image-manager' / 'library.json'
        before = manifest.read_bytes()
        result = self.sync(source='notion', target='local')
        self.assertEqual(result['operation']['code'], 'catalog_cycle')
        self.assertEqual(self.service.state()['inboxCount'], 0)
        self.assertEqual(manifest.read_bytes(), before)

    def test_real_notion_filename_normalization_keeps_metadata_text_and_deduplication(self):
        self.remote.normalize_filenames = True
        digest = self.annotate('Sample.png','Transparent_Name Space',group='My_Group Space')
        result = self.sync()
        self.assertEqual(result['operation']['status'],'completed')
        self.assertTrue(_reference_name(result['operation']['catalog']['reference']).startswith('Image_manager_catalog_-_'))
        self.assertEqual(self.remote.latest_catalog()['entries'][digest]['groupTitle'],'My_Group Space')
        self.assertEqual(self.remote.latest_catalog()['entries'][digest]['variantLabel'],'Transparent_Name Space')
        self.sync(request='normalized-repeat')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        self.service.annotate({'expectedRoot':str(self.root),'path':'Sample.png','sha256':digest,
            'groupTitle':'Temporary local label','variantLabel':'Temporary'})
        result = self.sync(source='notion',target='local',request='normalized-pull')
        self.assertEqual(result['operation']['status'],'completed')
        item = self.service.state()['items'][0]
        self.assertEqual(item['groupTitle'],'My_Group Space')
        self.assertEqual(item['variantLabel'],'Transparent_Name Space')
        self.assertEqual((self.root/'Sample.png').read_bytes(),self.data)

    def test_original_unknown_request_resumes_read_only_without_new_files_or_upload(self):
        self.remote.normalize_filenames = True
        first = self.sync()
        path = self.directory/'private'/('page-'+PAGE+'.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['operation'].update(status='unknown',code='catalog_attached_unverified')
        receipt = next(row for row in record['receipts'] if row.get('direction')=='catalog')
        receipt.update(status='attached_unverified')
        receipt.pop('reference',None)
        receipt.pop('requestId',None)  # Exact legacy 1.1.34 receipt shape.
        path.write_text(json.dumps(record),encoding='utf-8')
        later = png('blue')
        (self.root/'Later.png').write_bytes(later)
        count = len(self.remote.calls)
        resumed = self.sync()
        self.assertEqual(resumed['operation']['status'],'completed')
        self.assertEqual(resumed['operation']['id'],first['operation']['id'])
        self.assertEqual(resumed['operation']['requestId'],first['operation']['requestId'])
        self.assertEqual(resumed['operation']['items'],first['operation']['items'])
        self.assertEqual(resumed['operation']['catalog']['status'],'verified')
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[count:]))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        self.assertEqual((self.root/'Later.png').read_bytes(),later)
        self.assertEqual(len(self.service.state()['items']),1)

    def test_catalog_identity_accepts_only_the_two_documented_prefixes(self):
        readable = 'Image manager catalog - 20261101T010203123456Z-'+'a'*64+'.json'
        normalized = readable.replace(' ','_')
        self.assertTrue(_same_catalog_name(readable,normalized))
        self.assertFalse(_same_catalog_name(readable,normalized.replace('manager','Manager')))
        self.assertFalse(_same_catalog_name(readable,normalized.replace('a'*64,'b'*64)))
        self.assertFalse(_same_catalog_name(readable,readable.replace('Image manager','Image_manager')))

    def test_other_unknown_requests_are_not_resumed_or_reposted(self):
        first = self.sync()
        path = self.directory/'private'/('page-'+PAGE+'.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['operation'].update(status='unknown',code='file_transfer_unknown')
        path.write_text(json.dumps(record),encoding='utf-8')
        count = len(self.remote.calls)
        result = self.sync()
        self.assertEqual(result['operation']['status'],'unknown')
        self.assertEqual(result['operation']['id'],first['operation']['id'])
        self.assertEqual(len(self.remote.calls),count)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_completed_old_request_replays_after_newer_request_without_scan_or_upload(self):
        first = self.sync()
        second = self.sync(request='second')
        self.assertNotEqual(first['operation']['id'],second['operation']['id'])
        later = png('blue')
        (self.root/'Later.png').write_bytes(later)
        def no_scan(_):
            raise AssertionError('A known request must not scan new files.')
        self.service.scan = no_scan
        calls = len(self.remote.calls)
        persisted = ImageManagerNotion(self.service,self.directory/'private',
            rpc_factory=lambda root,page:self.remote,transfer_factory=lambda:self.remote)
        historical = persisted.operation('first')['operation']
        replayed = persisted.sync({'source':'local','target':'notion',
            'expectedRoot':str(self.root),'requestId':'first'})['operation']
        self.assertEqual(historical['id'],first['operation']['id'])
        self.assertEqual(replayed,historical)
        self.assertEqual(replayed['items'],first['operation']['items'])
        self.assertEqual(persisted.state()['operation']['id'],second['operation']['id'])
        self.assertEqual(len(self.remote.calls),calls)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        self.assertEqual(len(self.service.state()['items']),1)
        self.assertEqual((self.root/'Later.png').read_bytes(),later)

    def test_historical_catalog_unknown_can_only_resume_the_original_read_only_request(self):
        self.remote.normalize_filenames = True
        first = self.sync()
        path = self.directory/'private'/('page-'+PAGE+'.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['operation'].update(status='unknown',code='catalog_attached_unverified')
        receipt = next(row for row in record['receipts'] if row.get('direction')=='catalog')
        receipt.update(status='attached_unverified')
        receipt.pop('reference',None)
        receipt.pop('requestId',None)
        path.write_text(json.dumps(record),encoding='utf-8')
        second = self.sync(request='newer')
        self.assertEqual(self.provider.operation('first')['operation']['status'],'unknown')
        self.assertEqual(self.provider.operation('newer')['operation']['status'],'completed')
        def no_scan(_):
            raise AssertionError('Historical catalog verification must not scan.')
        self.service.scan = no_scan
        calls = len(self.remote.calls)
        self.provider.sync({'source':'local','target':'notion','expectedRoot':str(self.root),'requestId':'first'})
        self.provider.wait(5)
        resumed = self.provider.operation('first')['operation']
        self.assertEqual(resumed['status'],'completed')
        self.assertEqual(resumed['id'],first['operation']['id'])
        self.assertEqual(resumed['items'],first['operation']['items'])
        self.assertEqual(self.provider.operation('newer')['operation']['id'],second['operation']['id'])
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def fail_verified_completion_fixture(self):
        first = self.sync()
        path = self.directory/'private'/('page-'+PAGE+'.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['operation'].update(status='failed',code='notion_sync_failed')
        path.write_text(json.dumps(record),encoding='utf-8')
        return first,path,record

    def test_one_final_save_permission_error_preserves_verified_pending_and_read_only_recovery(self):
        real_save = notion_module._atomic_json
        failed = []
        def fail_once(path,record):
            if (record.get('operation') or {}).get('status') == 'completed' and not failed:
                failed.append(True)
                raise PermissionError(13,'Injected final receipt sharing failure')
            return real_save(path,record)
        with patch.object(notion_module,'_atomic_json',side_effect=fail_once):
            pending = self.sync()
        operation = pending['operation']
        self.assertEqual(operation['status'],'unknown')
        self.assertEqual(operation['code'],'verified_completion_unrecorded')
        self.assertTrue(operation['recheckable'])
        self.assertEqual(operation['recheckKind'],'verified_completion')
        self.assertEqual(operation['catalog']['status'],'verified')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        calls = len(self.remote.calls)
        resumed = self.sync()
        self.assertEqual(resumed['operation']['status'],'completed')
        self.assertEqual(resumed['operation']['id'],operation['id'])
        self.assertEqual(resumed['operation']['items'],operation['items'])
        self.assertEqual(resumed['operation']['verifiedOriginals'][0]['sha256'],hashlib.sha256(self.data).hexdigest())
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_legacy_all_verified_generic_failure_rechecks_original_payload_without_writes(self):
        first,path,record = self.fail_verified_completion_fixture()
        original_image_receipts = [dict(row) for row in record['receipts'] if row.get('direction')=='upload']
        self.assertTrue(self.provider.operation('first')['operation']['recheckable'])
        calls = len(self.remote.calls)
        def no_scan(_):raise AssertionError('Read-only recovery must not scan.')
        self.service.scan = no_scan
        resumed = self.sync()
        self.assertEqual(resumed['operation']['status'],'completed')
        self.assertEqual(resumed['operation']['id'],first['operation']['id'])
        self.assertEqual(resumed['operation']['items'],first['operation']['items'])
        self.assertEqual(len(resumed['operation']['verifiedOriginals']),1)
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        after = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual([row for row in after['receipts'] if row.get('direction')=='upload'],original_image_receipts)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_changed_original_payload_cannot_turn_verified_failure_into_completed_or_reupload(self):
        first,path,record = self.fail_verified_completion_fixture()
        reference = next(row['reference'] for row in record['receipts'] if row.get('direction')=='upload')
        self.remote.originals[reference] = png('blue')
        resumed = self.sync()
        self.assertEqual(resumed['operation']['status'],'failed')
        self.assertEqual(resumed['operation']['code'],'verified_original_hash_mismatch')
        self.assertFalse(resumed['operation']['recheckable'])
        calls = len(self.remote.calls)
        self.sync()
        self.assertEqual(len(self.remote.calls),calls)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        self.assertEqual((self.root/'Sample.png').read_bytes(),self.data)

    def test_incomplete_generic_failures_do_not_receive_read_only_completion_capability(self):
        first,path,record = self.fail_verified_completion_fixture()
        cases = [('remaining',lambda value:value['operation'].update(remainingTargets=['device'])),
            ('catalog',lambda value:value['operation']['catalog'].update(status='attached_unverified')),
            ('item',lambda value:value['operation']['items'][0].update(status='upload_unknown'))]
        import copy
        for label,change in cases:
            with self.subTest(label=label):
                modified = copy.deepcopy(record)
                change(modified)
                path.write_text(json.dumps(modified),encoding='utf-8')
                calls = len(self.remote.calls)
                state = self.provider.operation('first')
                self.assertFalse(state['operation']['recheckable'])
                replay = self.provider.sync({'source':'local','target':'notion','expectedRoot':str(self.root),'requestId':'first'})
                self.assertEqual(replay['operation']['status'],'failed')
                self.assertEqual(len(self.remote.calls),calls)
                self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_context_exit_error_cannot_erase_durable_completed_receipt(self):
        self.remote.exit_error = PermissionError(13,'Injected context cleanup failure')
        result = self.sync()
        self.assertEqual(result['operation']['status'],'completed')
        self.assertNotIn('code',result['operation'])
        self.assertEqual(result['operation']['catalog']['status'],'verified')
        self.assertFalse(result['operation']['recheckable'])
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))


if __name__ == '__main__':
    unittest.main()
