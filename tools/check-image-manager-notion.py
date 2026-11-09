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
        self.distinct_block_ids = False
        self.exit_error = None
        self.page_mode = page_mode
        self.page_writes = 0
        self.fail_page_before_write = self.fail_page_after_write = False
        self.page_error = None
        self.fetch_flags = {}
        self.on_fetch = None
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
            if self.on_fetch:self.on_fetch()
            return {'id': PAGE, 'metadata': {'type': 'page' if self.page_mode else 'folder'},
                'text': self.page_text if self.page_mode else '\n'.join('<image source="' + ref + '" />' for ref in self.originals),**self.fetch_flags}
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
            if self.page_error:raise self.page_error
            if self.fail_page_before_write:
                raise NotionSyncError('test_page_unknown', '页面写入回执未知。', unknown=True)
            assert arguments['page_id'] == PAGE and arguments['command'] == 'update_content'
            def save_source(match):
                source = html.unescape(match[2])
                if not source.startswith('file-upload://'):
                    return match[0]
                identifier = notion_module._source_id(source)
                item = self.uploads[identifier]
                name, data = item['name'], item['data']
                if self.normalize_filenames:
                    name = name.replace(' ', '_')
                block_id = str(uuid.uuid4()) if self.distinct_block_ids else identifier
                reference = 'notion-file-block://' + PAGE + '/' + block_id + '?name=' + quote(name)
                self.originals[reference] = data
                return match[1] + reference + match[3]
            for update in arguments['content_updates']:
                assert self.page_text.count(update['old_str']) == 1
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
        updates = [value['content_updates'] for action,value in self.remote.calls if action == 'page']
        self.assertEqual([row[0]['old_str'] for row in updates],
                         ['## Image\n\n<toggle>', notion_module.GALLERY_MARKER])
        writes = self.remote.page_writes
        result = self.sync(request='page-repeat')
        self.assertEqual(result['operation']['status'], 'completed')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (1,1,writes))

    def test_native_page_metadata_only_refreshes_caption_and_keeps_catalog_history(self):
        self.remote = FakeRemote(page_mode=True)
        item = self.service.state()['items'][0]
        image = self.remote.add_image('Sample - 7x5.png', self.data, 'Sample · 方案1 · 7×5')
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
        self.assertEqual(notion_module._image_refs(entity), [image])
        self.assertEqual(len([ref for ref in self.provider._refs(entity) if _catalog_identity(_reference_name(ref))]), 2)
        self.assertTrue(self.remote.page_text.endswith('\n\nUser notes after'))
        updates = [value['content_updates'] for action,value in self.remote.calls if action == 'page']
        self.assertEqual([row['old_str'] for row in updates[0]], ['Sample · 方案1 · 7×5', notion_module.GALLERY_MARKER])

    def test_native_page_verifies_a_new_image_with_a_distinct_block_id(self):
        self.remote = FakeRemote(page_mode=True)
        self.remote.distinct_block_ids = True
        operation = self.sync()['operation']
        self.assertEqual(operation['status'], 'completed', operation)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), (1,1,2))
        item = operation['items'][0]
        self.assertNotEqual(notion_module._source_id(item['reference']), item['uploadId'])
        self.assertEqual(self.remote.originals[item['reference']], self.data)

    def test_new_image_readback_requires_unique_caption_new_reference_and_matching_bytes(self):
        remote = FakeRemote(page_mode=True)
        caption = 'Current image'
        image = remote.add_image('Different filename.png', self.data, caption)
        expected = [{'source':'file-upload://'+str(uuid.uuid4()), 'caption':caption,
                     'sha256':hashlib.sha256(self.data).hexdigest()}]

        def verify(new_refs):
            entity = remote.call('fetch', {'id':PAGE})
            self.provider._verify_page_rows(remote, remote, entity, expected, new_refs=new_refs)

        with self.assertRaises(NotionSyncError):
            verify([])
        verify([image])
        remote.originals[image] = png('blue')
        with self.assertRaises(NotionSyncError):
            verify([image])
        remote.originals[image] = self.data
        duplicate = remote.add_image('Another name.png', self.data, caption)
        with self.assertRaises(NotionSyncError):
            verify([duplicate])

    def enable_standard_names(self, asset_type):
        entries = [{'path':item['path'],'sha256':item['sha256'],'assetType':asset_type}
                   for item in self.service.state()['items']]
        plan = self.service.naming_plan({'expectedRoot':str(self.root),'entries':entries})
        self.service.naming_apply({'expectedRoot':str(self.root),'planId':plan['planId']})
        state = self.service.state()
        self.assertTrue(state['standardNaming'])
        return state

    def test_standard_core_names_allow_same_basename_options_without_legacy_upload_markers(self):
        (self.root / 'Sample.png').rename(self.root / 'HeaderCapsule_v9_Final.png')
        blue = png('blue')
        (self.root / 'Temporary_story_Final.png').write_bytes(blue)
        self.service.scan({'expectedRoot':str(self.root)})
        for item in self.service.state()['items']:
            label = 'Option A' if item['sha256'] == hashlib.sha256(self.data).hexdigest() else 'Option B'
            self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
                'groupTitle':'HeaderCapsule','variantLabel':label})
        state = self.enable_standard_names('HeaderCapsule')
        self.assertEqual(len({item['path'] for item in state['items']}), 2)
        for item in state['items']:
            self.assertEqual(Path(item['path']).name, 'HeaderCapsule_7x5.png')
            self.assertEqual((item['canonicalName'],item['syncName']), ('HeaderCapsule_7x5.png','HeaderCapsule_7x5.png'))
        self.remote = FakeRemote(page_mode=True)
        result = self.sync(request='standard-options')
        self.assertEqual(result['operation']['status'], 'completed', result['operation'])
        images = [item for item in self.remote.uploads.values() if not item['name'].endswith('.json')]
        self.assertEqual([item['name'] for item in images], ['HeaderCapsule_7x5.png']*2)
        active = notion_module._image_refs(self.remote.call('fetch',{'id':PAGE}))
        self.assertEqual(len(active), 2)
        self.assertEqual(len({notion_module._source_id(reference) for reference in active}), 2)
        self.assertEqual({hashlib.sha256(self.remote.originals[reference]).hexdigest() for reference in active},
                         {hashlib.sha256(self.data).hexdigest(),hashlib.sha256(blue).hexdigest()})
        catalog = self.remote.latest_catalog()
        self.assertEqual(catalog['schemaVersion'],1)
        self.assertEqual({row['variantLabel'] for row in catalog['entries'].values()}, {'Option A','Option B'})
        for row in catalog['entries'].values():
            self.assertEqual(set(row), {'groupTitle','variantLabel','derivedFromId'})
            self.assertEqual(row['groupTitle'],'HeaderCapsule')
        counts = (self.remote.posts,self.remote.catalog_posts,self.remote.page_writes)
        self.sync(request='standard-options-repeat')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts,self.remote.page_writes), counts)
        self.assertEqual({(self.root/item['path']).read_bytes() for item in self.service.state()['items']}, {self.data,blue})

    def test_standard_adoption_keeps_verified_legacy_attachment_name_and_skips_original_reupload(self):
        self.annotate('Sample.png','Option A',group='HeaderCapsule')
        first = self.sync(request='legacy-before-standard')['operation']
        historical = notion_module._image_refs(self.remote.call('fetch',{'id':PAGE}))[0]
        historical_name = _reference_name(historical)
        self.assertEqual(historical_name, 'HeaderCapsule [方案 Option A] - 7x5.png')
        original_uploads = [key for key,value in self.remote.uploads.items() if not value['name'].endswith('.json')]
        state = self.enable_standard_names('HeaderCapsule')
        self.assertEqual(state['items'][0]['syncName'],'HeaderCapsule_7x5.png')
        completed = self.sync(request='standardize-existing')['operation']
        self.assertEqual(completed['status'],'completed',completed)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1),
                         'A filename-only migration must not republish an unchanged semantic catalogue')
        self.assertEqual(_reference_name(historical),historical_name)
        self.assertEqual([key for key,value in self.remote.uploads.items() if not value['name'].endswith('.json')],original_uploads)
        digest = hashlib.sha256(self.data).hexdigest()
        self.assertEqual(self.remote.latest_catalog()['entries'][digest]['groupTitle'],'HeaderCapsule')
        self.assertEqual(self.remote.originals[historical],self.data)
        before = (len(self.remote.calls),self.remote.posts,self.remote.catalog_posts)
        replay = self.provider.sync({'source':'local','target':'notion','expectedRoot':str(self.root),
                                     'requestId':'legacy-before-standard'})['operation']
        self.assertEqual(replay,first)
        self.assertEqual((len(self.remote.calls),self.remote.posts,self.remote.catalog_posts),before)

    def test_standard_page_caption_uses_canonical_purpose_without_claiming_old_file_was_renamed(self):
        self.remote = FakeRemote(page_mode=True)
        (self.root/'Sample.png').rename(self.root/'Mira_story_Final.png')
        self.service.scan({'expectedRoot':str(self.root)})
        self.sync(request='page-legacy-name')
        old_refs = notion_module._image_refs(self.remote.call('fetch',{'id':PAGE}))
        old_names = {_reference_name(reference) for reference in old_refs}
        upload_ids = {notion_module._source_id(reference) for reference in old_refs}
        self.enable_standard_names('LibraryHeader')
        result = self.sync(request='page-canonical-purpose')['operation']
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,2))
        entity = self.remote.call('fetch',{'id':PAGE})
        refs = notion_module._image_refs(entity)
        self.assertEqual({_reference_name(reference) for reference in refs},old_names)
        self.assertEqual({notion_module._source_id(reference) for reference in refs},upload_ids)
        captions = [html.unescape(caption).strip() for _,caption in notion_module.PAGE_IMAGE_RE.findall(notion_module._managed_text(entity))]
        self.assertEqual(captions,['LibraryHeader · 方案1 · 7×5'])
        self.assertNotIn('Final',captions[0])
        self.assertEqual(self.remote.latest_catalog()['entries'][hashlib.sha256(self.data).hexdigest()]['groupTitle'],'LibraryHeader')

    def test_standard_same_name_catalog_roundtrip_preserves_options_without_admitting_inbox(self):
        (self.root/'Other_Final.png').write_bytes(png('blue'))
        self.service.scan({'expectedRoot':str(self.root)})
        for index,item in enumerate(self.service.state()['items']):
            self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
                'groupTitle':'HeaderCapsule','variantLabel':'Option '+str(index+1)})
        self.enable_standard_names('HeaderCapsule')
        self.sync(request='standard-roundtrip-push')
        sink_root = self.directory/'standard-sink'
        sink_root.mkdir()
        sink = ImageManagerService(self.directory/'standard-sink-config.json')
        sink.configure({'root':str(sink_root),'notionPage':PAGE})
        provider = ImageManagerNotion(sink,self.directory/'standard-sink-private',
            rpc_factory=lambda root,page:self.remote,transfer_factory=lambda:self.remote)
        provider.sync({'source':'notion','target':'console','expectedRoot':str(sink_root),'requestId':'standard-roundtrip-pull'})
        result = provider.wait(5)
        self.assertEqual(result['operation']['status'],'needs_review',result['operation'])
        state = sink.state()
        self.assertEqual(state['items'],[])
        self.assertEqual(state['inboxCount'],2)
        candidates = state['plan']['candidates']
        self.assertEqual(len(candidates),2)
        expected = self.remote.latest_catalog()['entries']
        for candidate in candidates:
            incoming = candidate['incoming']
            self.assertEqual(incoming['groupTitle'],'HeaderCapsule')
            self.assertEqual(incoming['variantLabel'],expected[incoming['sha256']]['variantLabel'])
            self.assertEqual(hashlib.sha256((sink_root/incoming['path']).read_bytes()).hexdigest(),incoming['sha256'])
        self.assertEqual(self.remote.posts,2)

    def test_standard_library_unknown_external_item_blocks_entire_push_but_inbox_does_not(self):
        self.enable_standard_names('HeaderCapsule')
        unknown = self.root/'Clipboard_story_Final.png'
        # Even a uniquely suggested Steam size is not an explicit purpose.
        stream = io.BytesIO()
        with Image.new('RGB',(800,450),'blue') as picture:
            picture.save(stream,format='PNG')
        blue = stream.getvalue()
        unknown.write_bytes(blue)
        self.service.scan({'expectedRoot':str(self.root)})
        item = next(item for item in self.service.state()['items'] if item['path']==unknown.name)
        self.assertTrue(item['namingNeedsReview'])
        self.assertFalse(item.get('standardType'))
        operation = self.sync(request='standard-unknown-root')['operation']
        self.assertEqual((operation['status'],operation['code']),('failed','standard_naming_required'))
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(0,0))
        self.assertFalse(any(action in {'prepare','attach','page'} for action,_ in self.remote.calls))
        self.assertEqual(unknown.read_bytes(),blue)
        # Unconfirmed Inbox pictures are not indexed root originals and remain
        # outside this outward push, even if their purpose is not chosen yet.
        unknown.rename(self.root/'inbox'/unknown.name)
        self.service.scan({'expectedRoot':str(self.root)})
        completed = self.sync(request='standard-known-root-only')['operation']
        self.assertEqual(completed['status'],'completed',completed)
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        self.assertEqual((self.root/'inbox'/unknown.name).read_bytes(),blue)

    def test_native_page_appends_images_without_rebuilding_columns(self):
        remote = FakeRemote(page_mode=True)
        columns = ('<columns>\n<column ratio="34">\nFirst\n</column>\n'
                   '<column ratio="33">\nSecond\n</column>\n<column ratio="33">\nThird\n</column>\n</columns>')
        remote.page_text = remote.page_text.replace('<toggle>', columns + '\n\n<toggle>')
        entity = remote.call('fetch', {'id': PAGE})
        for closing in ('</columns>', '</image>'):
            with self.subTest(closing=closing):
                region = notion_module._page_region(entity)
                source = f'file-upload://{uuid.uuid4()}?name=Image.png&v=1'
                rows = [{'source':source, 'caption':'New [draft] <preview>'}]
                updates = notion_module._gallery_updates(region, rows, source, catalogue=False)
                self.assertEqual(updates[0]['old_str'], closing + '\n\n<toggle>')
                entity = notion_module._gallery_after_updates(entity, region, updates)
                self.assertIn(columns, entity['text'])
                self.assertIn('name=Image.png&amp;v=1', entity['text'])
                self.assertIn('New \\[draft\\] &lt;preview&gt;', entity['text'])

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
        self.assertTrue(all(item.get('reference') in observed for item in pending['items']))
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
        image = remote.add_image('Visible.png', self.data)
        rpc = CodexNotionRPC('unused', self.root, PAGE)
        entity = remote.call('fetch', {'id':PAGE})
        with patch.object(rpc, '_call', return_value=entity):
            rpc.call('fetch', {'id':PAGE})
        old = notion_module._page_region(entity)['text']
        caption = {'old_str':'Existing image','new_str':'Updated image caption'}
        source = 'file-upload://' + str(uuid.uuid4())
        addition = {'old_str':'</image>\n\n<toggle>',
                    'new_str':'</image>\n\n<image source="'+source+'">\nNew image\n</image>\n\n<toggle>'}
        valid = {'page_id':PAGE, 'command':'update_content', 'content_updates':[caption, addition]}
        rpc.allowed_upload_sources.add(source)
        with patch.object(rpc, '_call', return_value={'ok':True}) as call:
            rpc.call('page', valid)
            self.assertEqual(call.call_count, 1)
            bad_updates = [dict(valid, page_id=OTHER), dict(valid,command='replace_content'),
                dict(valid,content_updates=[{'old_str':old,'new_str':old.replace('## Image','## Updated')}]),
                dict(valid,content_updates=[{'old_str':'User notes after','new_str':'Outside text'}]),
                dict(valid,content_updates=[{'old_str':'Existing image','new_str':'</synced-block>'}]),
                dict(valid,content_updates=[{'old_str':image,'new_str':source}]),
                dict(valid,content_updates=[{'old_str':'Existing image','new_str':'![Foreign](https://example.invalid/image.png)'}]),
                dict(valid,content_updates=[{'old_str':'Existing image','new_str':addition['old_str']},addition]),
                dict(valid,content_updates=[caption, dict(caption)]),
                dict(valid,content_updates=[{'old_str':addition['old_str'],
                     'new_str':addition['new_str'].replace(source, 'notion-file-block://'+OTHER+'/'+OTHER)}])]
            for arguments in bad_updates:
                with self.assertRaises(NotionSyncError):
                    rpc.call('page', arguments)
            self.assertEqual(call.call_count, 1)
        duplicated = dict(entity, text=entity['text']+'\nExisting image')
        with patch.object(rpc, '_call', return_value=duplicated):
            rpc.call('fetch', {'id':PAGE})
        with self.assertRaises(NotionSyncError):
            rpc.call('page', valid)
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
        new = '<image source="'+foreign+'">\nFake image\n</image>\n</toggle>'
        with self.assertRaises(NotionSyncError):
            rpc.call('page', {'page_id':PAGE,'command':'update_content',
                'content_updates':[{'old_str':'</toggle>','new_str':new}]})
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
        self.assertNotEqual(pending['notionSync']['status'],'synced')
        self.assertIsNone(pending['notionSync']['syncedFingerprint'])
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))
        calls = len(self.remote.calls)
        resumed = self.sync()
        self.assertEqual(resumed['notionSync']['status'],'synced')
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

    def test_sync_status_is_local_read_only_and_connection_alone_is_not_export_verification(self):
        path = self.directory/'private'/('page-'+PAGE+'.json')
        self.assertEqual(self.provider.state()['notionSync']['status'],'unverified')
        self.assertFalse(path.exists())
        record = {'root':str(self.root),'pageId':PAGE,'receipts':[],'operation':None,'bridgeVerifiedAt':'2026-01-01T00:00:00Z'}
        path.write_text(json.dumps(record),encoding='utf-8')
        before,calls = path.read_bytes(),len(self.remote.calls)
        current = self.service.state()
        with patch.object(self.service,'state',side_effect=AssertionError('Reuse supplied core state')):
            with patch.object(self.service,'scan',side_effect=AssertionError('State must not scan')):
                summary = self.provider.state(local_state=current)
        self.assertTrue(summary['notion']['verified'])
        self.assertEqual(summary['notionSync']['status'],'unverified')
        self.assertIsNone(summary['notionSync']['syncedFingerprint'])
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len(self.remote.calls),calls)
        self.sync(request='readonly-probe')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['operation']['status'] = 'running'
        path.write_text(json.dumps(record),encoding='utf-8')
        lock = self.directory/'private'/('target-'+PAGE+'.lock')
        lock.write_bytes(b'')
        before,calls = path.read_bytes(),len(self.remote.calls)
        self.assertNotEqual(self.provider.state()['notionSync']['status'],'synced')
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(lock.read_bytes(),b'','A read-only busy probe must not initialize an empty lock')
        self.assertEqual(len(self.remote.calls),calls)

    def test_verified_sync_ignores_same_bytes_volatile_changes_and_unadopted_inbox_variants(self):
        first = self.sync()
        summary = first['notionSync']
        self.assertEqual(summary['status'],'synced')
        self.assertEqual(summary['localFingerprint'],summary['syncedFingerprint'])
        self.assertRegex(summary['localFingerprint'],r'^[0-9a-f]{64}$')
        self.assertEqual((summary['root'],summary['pageId']),(str(self.root),PAGE))
        self.assertEqual(summary['pendingCount'],0)
        self.assertTrue(summary['lastSyncedAt'])
        self.assertNotIn('exportSnapshot',first['operation'])
        (self.root/'Sample.png').write_bytes(self.data)
        self.service.scan({'expectedRoot':str(self.root)})
        self.service.import_files([('Sample [方案 B] - 7x5.png',png('blue'))],{'expectedRoot':str(self.root)})
        self.assertEqual(self.service.state()['inboxCount'],1)
        unchanged = self.provider.state()['notionSync']
        self.assertEqual(unchanged['status'],'synced')
        self.assertEqual(unchanged['localFingerprint'],summary['localFingerprint'])
        self.assertEqual(unchanged['pendingCount'],0)
        repeated = self.sync(request='repeat-with-inbox')
        self.assertEqual(repeated['notionSync']['status'],'synced')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_export_dirty_status_tracks_metadata_add_content_delete_and_undo(self):
        self.sync()
        item = self.service.state()['items'][0]
        self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
            'groupTitle':'HeaderCapsule','variantLabel':'B'})
        summary = self.provider.state()['notionSync']
        self.assertEqual((summary['status'],summary['pendingCount']),('pending',1))
        self.assertNotEqual(summary['localFingerprint'],summary['syncedFingerprint'])
        self.assertEqual(self.sync(request='metadata')['notionSync']['status'],'synced')
        (self.root/'Other.png').write_bytes(png('blue'))
        self.service.scan({'expectedRoot':str(self.root)})
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        self.assertEqual(self.sync(request='added')['notionSync']['status'],'synced')
        (self.root/'Sample.png').write_bytes(png('green'))
        self.assertEqual(self.provider.state()['notionSync']['reason'],'local_changed')
        self.service.scan({'expectedRoot':str(self.root)})
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        self.assertEqual(self.sync(request='content')['notionSync']['status'],'synced')
        other = next(item for item in self.service.state()['items'] if item['path']=='Other.png')
        request = {'expectedRoot':str(self.root),'path':other['path'],'sha256':other['sha256'],'requestId':'a'*32}
        self.service.delete(request)
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        self.assertEqual(self.sync(request='deleted')['notionSync']['status'],'synced')
        self.service.delete_restore({'expectedRoot':str(self.root),'requestId':request['requestId']})
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        self.assertEqual((self.root/'Other.png').read_bytes(),png('blue'))

    def test_actual_basename_counts_but_same_basename_relative_path_does_not(self):
        original = self.sync()['notionSync']['localFingerprint']
        (self.root/'subfolder').mkdir()
        (self.root/'Sample.png').rename(self.root/'subfolder/Sample.png')
        self.service.scan({'expectedRoot':str(self.root)})
        self.assertEqual(self.provider.state()['notionSync']['status'],'synced')
        self.assertEqual(self.provider.state()['notionSync']['localFingerprint'],original)
        (self.root/'subfolder/Sample.png').rename(self.root/'subfolder/Renamed.png')
        self.service.scan({'expectedRoot':str(self.root)})
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')

    def test_verified_export_is_bound_to_root_and_page_and_missing_original_is_pending(self):
        self.sync()
        other = self.directory/'other-root'
        other.mkdir()
        (other/'Sample.png').write_bytes(self.data)
        self.service.configure({'root':str(other),'notionPage':PAGE})
        self.service.scan({'expectedRoot':str(other)})
        summary = self.provider.state()['notionSync']
        self.assertEqual(summary['status'],'unverified')
        self.assertIsNone(summary['syncedFingerprint'])
        self.service.configure({'root':str(self.root),'notionPage':OTHER})
        self.assertEqual(self.provider.state()['notionSync']['status'],'unverified')
        self.service.configure({'root':str(self.root),'notionPage':PAGE})
        self.assertEqual(self.provider.state()['notionSync']['status'],'synced')
        (self.root/'Sample.png').unlink()
        summary = self.provider.state()['notionSync']
        self.assertEqual((summary['status'],summary['reason']),('pending','local_changed'))
        self.assertIsNone(summary['localFingerprint'])

    def test_failed_unknown_and_partial_operations_never_create_a_green_marker(self):
        first,path,record = self.fail_verified_completion_fixture()
        self.assertEqual(self.provider.state()['notionSync']['status'],'failed')
        self.assertEqual(self.provider.state()['notionSync']['syncedFingerprint'],first['notionSync']['syncedFingerprint'])
        (self.root/'Sample.png').write_bytes(png('blue'))
        self.service.scan({'expectedRoot':str(self.root)})
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        self.remote.fail_upload = True
        self.sync(request='unknown-new-content')
        self.assertEqual(self.provider.state()['notionSync']['status'],'pending')
        current = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(current['verifiedExports'],record['verifiedExports'])
        self.remote.fail_upload = False
        device = self.directory/'device'
        device.mkdir()
        self.service.configure({'root':str(self.root),'deviceRoot':str(device)})
        # A known partial Notion+device request cannot borrow an old green flag.
        current['operation'].update(status='completed',remainingTargets=['device'])
        current['verifiedExports'] = {}
        path.write_text(json.dumps(current),encoding='utf-8')
        self.assertNotEqual(self.provider.state()['notionSync']['status'],'synced')

    def test_verified_marker_uses_start_snapshot_even_when_metadata_changes_during_upload(self):
        original = self.provider.state()['notionSync']['localFingerprint']
        def edit_once():
            self.remote.before_upload = None
            item = self.service.state()['items'][0]
            self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
                'groupTitle':'Later local purpose','variantLabel':'Later option'})
        self.remote.before_upload = edit_once
        completed = self.sync()
        self.assertEqual(completed['operation']['status'],'completed')
        self.assertEqual(completed['notionSync']['status'],'pending')
        self.assertEqual(completed['notionSync']['syncedFingerprint'],original)
        self.assertNotEqual(completed['notionSync']['localFingerprint'],original)
        self.assertEqual(self.remote.latest_catalog()['entries'][hashlib.sha256(self.data).hexdigest()]['groupTitle'],'Sample')
        self.assertEqual(self.sync(request='later-intent')['notionSync']['status'],'synced')
        self.assertEqual(self.remote.posts,1)

    def test_read_only_catalog_recovery_marks_only_proven_original_snapshot_and_never_legacy_guess(self):
        first = self.sync()
        path = self.directory/'private'/('page-'+PAGE+'.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['verifiedExports'] = {}
        record['operation'].update(status='unknown',code='catalog_attached_unverified')
        receipt = next(row for row in record['receipts'] if row.get('direction')=='catalog')
        receipt['status'] = 'attached_unverified'
        path.write_text(json.dumps(record),encoding='utf-8')
        calls = len(self.remote.calls)
        resumed = self.sync()
        self.assertEqual(resumed['notionSync']['status'],'synced')
        self.assertEqual(resumed['notionSync']['syncedFingerprint'],first['notionSync']['syncedFingerprint'])
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        record = json.loads(path.read_text(encoding='utf-8'))
        record['verifiedExports'] = {}
        record['operation'].pop('exportSnapshot',None)
        record['operation'].pop('exportCatalogSha256',None)
        record['operation'].update(status='unknown',code='catalog_attached_unverified')
        path.write_text(json.dumps(record),encoding='utf-8')
        legacy = self.sync()
        self.assertEqual(legacy['operation']['status'],'completed')
        self.assertEqual(legacy['notionSync']['status'],'unverified')
        self.assertEqual((self.remote.posts,self.remote.catalog_posts),(1,1))

    def test_empty_root_never_claims_remote_history_was_deleted_or_verified_by_empty_subset(self):
        first = self.sync()
        item = self.service.state()['items'][0]
        self.service.delete({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],'requestId':'a'*32})
        result = self.sync(request='empty-root')
        self.assertEqual(result['operation']['status'],'completed')
        self.assertEqual((result['notionSync']['status'],result['notionSync']['reason']),('unverified','empty_library'))
        self.assertEqual(result['notionSync']['syncedFingerprint'],first['notionSync']['syncedFingerprint'])
        self.assertTrue(any(data==self.data for data in self.remote.originals.values()))
        self.assertEqual(self.remote.posts,1)

    def pending_original_fixture(self, later=True):
        self.remote = FakeRemote(page_mode=True)
        if later:
            (self.root/'ZLater.png').write_bytes(png('blue'))
            self.service.scan({'expectedRoot':str(self.root)})
        self.remote.page_error = NotionSyncError('notion_tool_error','Original attach failed.')
        failed = self.sync(source='console')
        self.remote.page_error = None
        self.assertEqual(failed['operation']['code'],'notion_tool_error')
        self.assertTrue(failed['operation']['recheckable'])
        self.assertEqual(failed['operation']['recheckKind'],'upload_receipt')
        path = self.directory/'private'/('page-'+PAGE+'.json')
        return failed,path,json.loads(path.read_text(encoding='utf-8'))

    def retry_original(self, request='retry-new', retry_of='first'):
        self.provider.sync({'source':'console','target':'notion','expectedRoot':str(self.root),
            'requestId':request,'retryOf':retry_of})
        return self.provider.wait(5)

    def test_original_recheck_is_read_only_and_legacy_receipt_gets_bounded_explicit_retry_offer(self):
        failed,path,record = self.pending_original_fixture()
        receipt = record['receipts'][0]
        for key in ('requestId','operationId','root','pageId','exportFingerprint','uploadSource'):
            receipt.pop(key,None)
        original_receipt = dict(receipt)
        path.write_text(json.dumps(record),encoding='utf-8')
        calls,posts = len(self.remote.calls),self.remote.posts
        checked = self.sync(source='console')
        operation = checked['operation']
        self.assertEqual((operation['id'],operation['requestId']),(failed['operation']['id'],'first'))
        self.assertEqual((operation['status'],operation['code']),('failed','recovery_unavailable'))
        self.assertTrue(operation['retryable'])
        self.assertEqual(operation['retryOf'],'first')
        self.assertEqual(len(operation['missingOriginals']),2)
        self.assertEqual(self.remote.posts,posts)
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        self.assertNotIn('recoveryEvidence',operation)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['receipts'][0],original_receipt)
        calls = len(self.remote.calls)
        self.sync(source='console')
        self.assertEqual(len(self.remote.calls),calls,'Same old request never starts the new retry intent')

    def test_new_explicit_retry_uploads_missing_only_and_preserves_old_evidence_and_request_replay(self):
        _,path,record = self.pending_original_fixture()
        old = dict(record['receipts'][0])
        self.sync(source='console')
        result = self.retry_original()
        self.assertEqual(result['operation']['status'],'completed')
        self.assertEqual(result['notionSync']['status'],'synced')
        self.assertEqual(self.remote.posts,3)  # One orphan from old intent, two explicitly authorized missing originals.
        after = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(next(row for row in after['receipts'] if row['id']==old['id']),old)
        new = next(row for row in after['receipts'] if old['id'] in row.get('supersedesReceiptIds',[]))
        self.assertEqual((new['retryOf'],new['requestId']),('first','retry-new'))
        self.assertTrue(new['uploadSource'].startswith('file-upload://'))
        self.assertNotIn('uploadSource',json.dumps(result['operation']))
        self.assertNotIn('SECRET_SHOULD_NEVER_BE_SAVED',path.read_text(encoding='utf-8'))
        calls,posts = len(self.remote.calls),self.remote.posts
        self.provider.sync({'source':'console','target':'notion','expectedRoot':str(self.root),'requestId':'retry-new'})
        self.assertEqual((len(self.remote.calls),self.remote.posts),(calls,posts))
        with self.assertRaises(NotionSyncError):self.retry_original(request='first')
        with self.assertRaises(NotionSyncError):
            self.provider.sync({'source':'console','target':'notion','expectedRoot':str(self.root),
                                'requestId':'null-retry','retryOf':None})

    def test_retry_local_scope_change_stops_before_prepare_and_new_snapshot_can_be_checked(self):
        self.pending_original_fixture()
        self.sync(source='console')
        item = self.service.state()['items'][0]
        self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
            'groupTitle':'Changed purpose','variantLabel':'Changed'})
        calls,posts = len(self.remote.calls),self.remote.posts
        with self.assertRaises(NotionSyncError):self.retry_original()
        self.assertEqual((len(self.remote.calls),self.remote.posts),(calls,posts))
        blocked = self.sync(source='console',request='new-snapshot')
        self.assertEqual(blocked['operation']['code'],'upload_receipt_unresolved')
        self.assertTrue(blocked['operation']['recheckable'])
        self.assertEqual(self.remote.posts,posts)
        checked = self.sync(source='console',request='new-snapshot')
        self.assertTrue(checked['operation']['retryable'])
        self.assertEqual(checked['operation']['retryOf'],'new-snapshot')

    def test_target_cas_change_after_recheck_refuses_every_new_upload(self):
        _,path,record = self.pending_original_fixture()
        self.sync(source='console')
        original_text = self.remote.page_text
        self.remote.page_text = self.remote.page_text.replace('## Image','## Image\nNew user note',1)
        prepares = sum(action=='prepare' for action,_ in self.remote.calls)
        result = self.retry_original()
        self.assertEqual((result['operation']['status'],result['operation']['code']),('failed','recovery_evidence_stale'))
        self.assertEqual(sum(action=='prepare' for action,_ in self.remote.calls),prepares)
        self.assertEqual(self.remote.posts,1)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['receipts'][0],record['receipts'][0])
        self.remote.page_text = original_text
        reads = []
        def change_local_during_fetch():
            reads.append(True)
            if len(reads)==2:
                item = self.service.state()['items'][0]
                self.service.annotate({'expectedRoot':str(self.root),'path':item['path'],'sha256':item['sha256'],
                    'groupTitle':'Changed during read','variantLabel':'B'})
        self.remote.on_fetch = change_local_during_fetch
        failed = self.retry_original(request='concurrent-local-edit')
        self.assertEqual(failed['operation']['code'],'recovery_evidence_stale')
        self.assertEqual(sum(action=='prepare' for action,_ in self.remote.calls),prepares)

    def test_recovery_negative_evidence_rejects_truncation_unknown_omission_and_unclosed_region(self):
        _,path,baseline = self.pending_original_fixture()
        original_text = self.remote.page_text
        cases = [({'truncated':True},original_text),({'metadata':{'type':'page','truncated':True}},original_text),
            ({'unknown_block_count':1},original_text),({'omitted_children':['x']},original_text),
            ({},original_text.replace('<toggle>','<unknown-block />\n<toggle>',1)),
            ({},original_text.replace('</synced-block>','',1)),
            ({},original_text.replace('<toggle>','<columns><column>\n<toggle>',1))]
        for flags,text in cases:
            with self.subTest(flags=flags):
                path.write_text(json.dumps(baseline),encoding='utf-8')
                self.remote.fetch_flags,self.remote.page_text = flags,text
                calls = len(self.remote.calls)
                result = self.sync(source='console')
                self.assertNotEqual(result['operation'].get('retryable'),True)
                self.assertNotEqual(result['notionSync']['status'],'synced')
                self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
                self.assertEqual(self.remote.posts,1)

    def test_recovery_refuses_native_file_inside_or_outside_owned_gallery(self):
        _,path,baseline = self.pending_original_fixture()
        text = self.remote.page_text
        ref = 'notion-file-block://'+PAGE+'/'+str(uuid.uuid4())+'?name=Sample.png'
        self.remote.originals[ref] = self.data
        for outside in (False,True):
            with self.subTest(outside=outside):
                path.write_text(json.dumps(baseline),encoding='utf-8')
                tag = '<file source="'+ref+'">Original image</file>'
                self.remote.page_text = text+'\n'+tag if outside else text.replace('</toggle>',tag+'\n</toggle>',1)
                result = self.sync(source='console')
                self.assertEqual(result['operation']['code'],'recovery_attachment_review')
                self.assertNotEqual(result['operation'].get('retryable'),True)
                self.assertEqual(self.remote.posts,1)

    def test_recheck_already_attached_originals_complete_without_upload_but_reject_wrong_caption(self):
        _,path,record = self.pending_original_fixture(later=False)
        self.remote.add_image('Sample - 7x5.png',self.data,caption='Sample · 方案1 · 7×5')
        self.remote.add_catalog({
            row['sha256']:row['metadata'] for row in record['operation']['exportSnapshot']['entries']})
        calls,posts = len(self.remote.calls),self.remote.posts
        result = self.sync(source='console')
        self.assertEqual((result['operation']['status'],result['notionSync']['status']),('completed','synced'))
        self.assertEqual(self.remote.posts,posts)
        self.assertTrue(all(action in {'fetch','download'} for action,_ in self.remote.calls[calls:]))
        path.write_text(json.dumps(record),encoding='utf-8')
        self.remote.page_text = self.remote.page_text.replace('Sample · 方案1 · 7×5','Wrong external caption')
        failed = self.sync(source='console')
        self.assertNotEqual(failed['notionSync']['status'],'synced')
        self.assertNotEqual(failed['operation']['status'],'completed')

    def test_target_mutation_between_negative_fetches_and_legacy_without_snapshot_never_authorize_retry(self):
        _,path,record = self.pending_original_fixture()
        reads = []
        def change_second_fetch():
            reads.append(True)
            if len(reads)==2:self.remote.page_text=self.remote.page_text.replace('## Image','## Image\nChanged',1)
        self.remote.on_fetch = change_second_fetch
        result = self.sync(source='console')
        self.assertEqual(result['operation']['code'],'recovery_target_changed')
        self.assertNotEqual(result['operation'].get('retryable'),True)
        self.assertEqual(self.remote.posts,1)
        self.remote.on_fetch = None
        record['operation'].pop('exportSnapshot',None)
        path.write_text(json.dumps(record),encoding='utf-8')
        calls = len(self.remote.calls)
        result = self.sync(source='console')
        self.assertFalse(result['operation']['recheckable'])
        self.assertEqual(len(self.remote.calls),calls)
        with self.assertRaises(NotionSyncError):self.retry_original()


if __name__ == '__main__':
    unittest.main()
