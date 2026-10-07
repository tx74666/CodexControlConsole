"""Resource catalogue checks; all network fixtures are explicit official schemas."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_library import DocumentLibraryService
import resource_library as resources


UID = '1234567890abcdef1234567890abcdef'
# Actual shape returned by the official read-only Car search on 2026-10-07.
LEGACY_UID = 'hliAt7xc6YU2XjXh5G4lzmQwFmR'
SKETCHFAB = {'results': [{'uid': UID, 'name': 'Earth model',
    'viewerUrl': 'https://sketchfab.com/3d-models/earth-' + UID,
    'thumbnails': {'images': [{'width': 1920, 'url': 'https://media.sketchfab.com/earth-large.jpg'},
                               {'width': 720, 'url': 'https://media.sketchfab.com/earth.jpg'}]},
    'license': {'label': 'CC Attribution'}, 'user': {'displayName': 'Artist'}}]}
LEGACY_SKETCHFAB = json.loads(json.dumps(SKETCHFAB))
LEGACY_SKETCHFAB['results'][0].update({'uid': LEGACY_UID, 'name': 'Future Car',
    'viewerUrl': 'https://sketchfab.com/3d-models/none-' + LEGACY_UID,
    'uri': 'https://api.sketchfab.com/v3/models/' + LEGACY_UID})
POLYHAVEN = {'stone_chair': {'name': 'Stone Chair', 'tags': ['chair', 'stone'],
    'categories': ['furniture'], 'authors': {'Author': 'https://example.com/'},
    'thumbnail_url': 'https://cdn.polyhaven.com/asset_img/stone_chair.png'},
    'wood_floor': {'name': 'Wood Floor', 'tags': ['wood', 'floor'], 'categories': ['floor'],
    'thumbnail_url': 'https://cdn.polyhaven.com/asset_img/wood_floor.png'}}


class CatalogueChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='console-resources-check-')
        self.base = Path(self.temporary.name)
        self.root = self.base / 'existing-database'
        self.root.mkdir()
        self.settings = self.base / 'documents.json'
        self.settings.write_text(json.dumps({'root': str(self.root)}), encoding='utf-8')
        self.documents = DocumentLibraryService(self.settings)
        self.service = resources.ResourceLibraryService(self.documents)
        self.store = self.root / resources.STORE_RELATIVE

    def tearDown(self):
        self.temporary.cleanup()

    def search(self, **kwargs):
        return self.service.search({'expectedRoot': str(self.root), 'q': 'earth', **kwargs})

    def save(self, **kwargs):
        return self.service.save({'expectedRoot': str(self.root),
            'expectedRevision': self.service.state()['revision'], **kwargs})

    def test_reading_never_networks_or_creates_store(self):
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected network')):
            state = self.service.state()
            self.assertEqual((state['revision'], state['items']), (0, []))
            self.assertEqual(list(self.root.iterdir()), [])
            with self.assertRaises(resources.ResourceLibraryConflict):
                self.service.save({'name': 'No root', 'url': 'https://example.com/a', 'expectedRevision': 0})
            self.assertEqual(list(self.root.iterdir()), [])

    def test_canonical_identity_and_public_url_rules(self):
        cases = [
            ('https://assetstore.unity.com/packages/vfx/shaders/free-slash-vfx-309498?utm_source=chatgpt#preview',
             'https://marketplace.unity.com/packages/vfx/shaders/new-name-309498', 'unity:309498'),
            ('https://sketchfab.com/3d-models/earth-' + UID + '?utm_source=chatgpt',
             'https://sketchfab.com/models/' + UID, 'sketchfab:' + UID),
            ('https://polyhaven.com/a/stone_chair?utm_medium=chat#read',
             'https://www.polyhaven.com/a/stone_chair', 'polyhaven:stone_chair'),
            ('https://example.com/a/?utm_source=x&size=large#preview',
             'https://example.com/a?size=large', 'url:https://example.com/a?size=large'),
        ]
        for first, second, identity in cases:
            self.assertEqual(resources.canonical_resource(first)[0], identity)
            self.assertEqual(resources.canonical_resource(second)[0], identity)
        for url in ('http://example.com/a', 'https://name:secret@example.com/a', 'https://localhost/a',
                    'https://127.0.0.1/a', 'https://[::1]/a', 'https://10.0.0.1/a',
                    'https://169.254.169.254/a', 'https://2130706433/a', 'https://0177.0.0.1/a',
                    'https://host.internal/a', 'https://example.com:8080/a'):
            with self.subTest(url=url), self.assertRaises(resources.ResourceLibraryError):
                resources.public_https_url(url)

    def test_repeat_query_cache_selection_refresh_and_reopen(self):
        with patch.object(resources, '_fetch_json', return_value=SKETCHFAB) as fetch:
            found = self.search()
            self.assertFalse(found['cached'])
            self.assertEqual(found['items'][0]['previewUrl'], 'https://media.sketchfab.com/earth.jpg')
            self.assertIn('CC Attribution', found['items'][0]['license'])
            self.assertEqual(found['items'][0]['status'], 'candidate')
            identifier = found['items'][0]['id']
            chosen = self.save(id=identifier, status='planned', notes='For my project')
            first_time, revision = found['searchTime'], chosen['revision']
            repeated = self.search(q=' EARTH ')
            self.assertTrue(repeated['cached'])
            self.assertEqual(repeated['searchTime'], first_time)
            self.assertEqual(repeated['revision'], revision)
            self.assertEqual(fetch.call_count, 1)
            changed = json.loads(json.dumps(SKETCHFAB))
            changed['results'][0]['name'] = 'Changed by provider'
            with patch.object(resources, '_fetch_json', return_value=changed):
                refreshed = self.search(refresh=True)
                new_query = self.search(q='planet earth')
            item = new_query['items'][0]
            self.assertEqual((item['status'], item['notes'], item['name']), ('planned', 'For my project', 'Earth model'))
            self.assertEqual(len(item['queries']), 2)
            self.assertGreaterEqual(len(item['provenance']), 3)
            reopened = resources.ResourceLibraryService(DocumentLibraryService(self.settings)).state()
            self.assertEqual(len(reopened['items']), 1)
            self.assertEqual(reopened['items'][0], item)
            with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected network')):
                cached = self.search(q='planet earth')
                self.assertTrue(cached['cached'])

    def test_real_car_legacy_uid_shape_is_kept_with_hex_results(self):
        mixed = {'results': LEGACY_SKETCHFAB['results'] + SKETCHFAB['results']}
        with patch.object(resources, '_fetch_json', return_value=mixed):
            result = self.search(q='Car')
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['skippedCount'], 0)
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['items'][0]['identity'], 'sketchfab:' + LEGACY_UID)
        self.assertEqual(result['items'][0]['url'], 'https://sketchfab.com/models/' + LEGACY_UID)
        self.assertEqual(result['items'][1]['identity'], 'sketchfab:' + UID)
        for route in ('https://sketchfab.com/models/' + LEGACY_UID,
                      'https://www.sketchfab.com/3d-models/none-' + LEGACY_UID):
            self.assertEqual(resources.canonical_resource(route)[0], 'sketchfab:' + LEGACY_UID)
        self.assertNotEqual(resources.canonical_resource('https://sketchfab.com/models/' + LEGACY_UID)[0],
                            resources.canonical_resource('https://sketchfab.com/models/' + LEGACY_UID.lower())[0])
        self.assertEqual(resources.canonical_resource('https://sketchfab.com/models/' + UID.upper())[0], 'sketchfab:' + UID)
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('cached query must not fetch')):
            cached = self.search(q='car')
        self.assertTrue(cached['cached'])
        self.assertEqual(cached['items'], result['items'])

    def test_previously_saved_legacy_url_identity_id_and_selection_survive(self):
        old_url = 'https://www.sketchfab.com/3d-models/future-car-' + LEGACY_UID
        old_identity = 'url:' + old_url
        old_item = self.service._candidate({'name': 'My selected car', 'url': old_url, 'kind': 'model'})
        old_item.update({'identity': old_identity, 'id': resources._identifier(old_identity),
                         'url': old_url, 'status': 'planned', 'notes': 'Keep for the Unity scene',
                         'license': 'Checked license', 'provenance': ['Previously collected link']})
        old_id = old_item['id']
        data = {'version': 1, 'revision': 1, 'items': [old_item], 'searches': []}
        self.store.parent.mkdir(parents=True)
        self.store.write_text(json.dumps(data), encoding='utf-8')
        initial = self.service.state()['items'][0]
        self.assertEqual((initial['id'], initial['identity'], initial['url']), (old_id, old_identity, old_url))
        with patch.object(resources, '_fetch_json', return_value=LEGACY_SKETCHFAB):
            result = self.search(q='Car')
        self.assertEqual(len(result['items']), 1)
        item = result['items'][0]
        self.assertEqual((item['id'], item['identity'], item['url']), (old_id, old_identity, old_url))
        self.assertEqual((item['name'], item['status'], item['notes'], item['license']),
                         ('My selected car', 'planned', 'Keep for the Unity scene', 'Checked license'))
        self.assertIn('Previously collected link', item['provenance'])
        self.assertEqual(item['queries'][0]['query'], 'Car')
        duplicate = self.save(name='Incoming API title', url='https://sketchfab.com/models/' + LEGACY_UID)
        self.assertEqual(len(duplicate['items']), 1)
        self.assertEqual(duplicate['item']['id'], old_id)
        reopened = resources.ResourceLibraryService(DocumentLibraryService(self.settings)).state()
        self.assertEqual(reopened['items'][0]['id'], old_id)

    def test_bad_result_is_visible_partial_warning_and_all_bad_is_error(self):
        mixed = {'results': [None, {'uid': 'bad/token', 'name': 'Unsafe token'}, *LEGACY_SKETCHFAB['results']]}
        with patch.object(resources, '_fetch_json', return_value=mixed):
            result = self.search(q='Car')
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['identity'], 'sketchfab:' + LEGACY_UID)
        self.assertEqual(result['skippedCount'], 2)
        self.assertEqual(len(result['warnings']), 2)
        self.assertIn('UID', result['warnings'][1])
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('cached query must not fetch')):
            cached = self.search(q='Car')
        self.assertEqual((cached['skippedCount'], cached['warnings']), (2, result['warnings']))
        before = self.store.read_bytes()
        with patch.object(resources, '_fetch_json', return_value={'results': [{'uid': 'bad/token'}]}):
            with self.assertRaises(resources.ResourceLibraryError) as failed:
                self.search(q='All invalid')
        self.assertEqual(failed.exception.status, 502)
        self.assertEqual(self.store.read_bytes(), before)

    def test_old_search_cache_defaults_warning_fields_without_rewrite(self):
        with patch.object(resources, '_fetch_json', return_value=SKETCHFAB):
            self.search()
        data = json.loads(self.store.read_text(encoding='utf-8'))
        data['searches'][0].pop('skippedCount')
        data['searches'][0].pop('warnings')
        raw = json.dumps(data).encode('utf-8')
        self.store.write_bytes(raw)
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('cached query must not fetch')):
            result = self.search()
        self.assertEqual((result['skippedCount'], result['warnings']), (0, []))
        self.assertEqual(self.store.read_bytes(), raw)

    def test_external_sources_cannot_be_posted_as_direct_searches(self):
        external = [p for p in resources.PROVIDERS if p['mode'] == 'external']
        self.assertEqual({p['id'] for p in external}, {'itchio', 'unity', 'fab', 'cgtrader'})
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('external source must not fetch')), \
             patch.object(resources, '_fetch_text', side_effect=AssertionError('external source must not fetch')):
            for source in external:
                with self.subTest(source=source['id']), self.assertRaises(resources.ResourceLibraryError):
                    self.search(provider=source['id'], kind=source['defaultKind'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_catalog_results_use_shared_candidate_validation_and_preserve_choices(self):
        row = {'name': 'A catalogue model', 'url': 'https://kenney.nl/assets/car-kit',
               'kind': 'model', 'previewUrl': 'https://kenney.nl/media/car-kit.png',
               'license': 'CC0', 'price': '免費', 'provenance': ['Official catalogue']}
        with patch.object(resources, 'search_catalog', return_value=[row, {**row, 'url': 'https://127.0.0.1/private'}]):
            result = self.search(provider='kenney', q='car', kind='model')
        self.assertEqual((len(result['items']), result['skippedCount']), (1, 1))
        self.assertEqual(result['items'][0]['provider'], 'kenney')
        selected = self.save(id=result['items'][0]['id'], status='saved', notes='My choice')
        with patch.object(resources, 'search_catalog', return_value=[{**row, 'license': 'Changed', 'name': 'Changed'}]):
            refreshed = self.search(provider='kenney', q='car', kind='model', refresh=True)
        self.assertEqual((refreshed['items'][0]['name'], refreshed['items'][0]['license'], refreshed['items'][0]['notes']),
                         ('A catalogue model', 'CC0', 'My choice'))
        self.assertEqual(refreshed['items'][0]['id'], selected['item']['id'])
        with patch.object(resources, 'search_catalog', side_effect=ValueError('Catalogue structure changed')):
            with self.assertRaises(resources.ResourceLibraryError) as failed:
                self.search(provider='kenney', q='new query', kind='model')
        self.assertEqual(failed.exception.status, 502)

    def test_manual_duplicate_import_preserves_confirmed_choice(self):
        first = self.save(name='Slash', kind='vfx',
            url='https://assetstore.unity.com/packages/vfx/shaders/free-slash-vfx-309498?utm_source=x',
            status='saved', provenance='User supplied link')
        second = self.save(name='Slash', kind='vfx',
            url='https://marketplace.unity.com/packages/vfx/shaders/free-slash-vfx-309498',
            status='candidate', provenance='Second conversation')
        self.assertEqual(len(second['items']), 1)
        self.assertEqual(first['item']['id'], second['item']['id'])
        self.assertEqual(second['item']['status'], 'saved')
        self.assertEqual(second['item']['provenance'], ['User supplied link', 'Second conversation'])
        explicit = self.save(id=second['item']['id'], status='candidate')
        self.assertEqual(explicit['item']['status'], 'candidate')

    def test_confirmed_resource_reuse_preserves_metadata_and_notes(self):
        first = self.save(name='Brackeys VFX', kind='vfx', url='https://example.com/vfx',
            previewUrl='https://images.example.com/vfx.png', description='Confirmed effects bundle',
            license='CC0', price='免費', notes='Use after visual review', status='saved')
        repeated = self.save(name='New webpage title', url='https://example.com/vfx?utm_source=chat',
            kind='other', previewUrl='https://images.example.com/new.png', description='A changed page',
            license='待核对', price='待核對', notes='', status='candidate')
        for key in ('id', 'name', 'kind', 'previewUrl', 'description', 'license', 'price', 'notes', 'status'):
            self.assertEqual(repeated['item'][key], first['item'][key], key)
        appended = self.save(name='New webpage title', url='https://example.com/vfx',
            notes='Check the particle settings', status='planned')
        self.assertEqual(appended['item']['notes'], 'Use after visual review\n\nCheck the particle settings')
        self.assertEqual(appended['item']['status'], 'planned')
        duplicate_note = self.save(name='New webpage title', url='https://example.com/vfx',
            notes='Check the particle settings')
        self.assertEqual(duplicate_note['item']['notes'], appended['item']['notes'])
        explicit_clear = self.save(id=first['item']['id'], notes='')
        self.assertEqual(explicit_clear['item']['notes'], '')
        explicit_replacement = self.save(id=first['item']['id'], notes='A deliberate replacement')
        self.assertEqual(explicit_replacement['item']['notes'], 'A deliberate replacement')

    def test_confirmed_unknown_fields_accept_clear_metadata_and_candidate_can_be_checked(self):
        first = self.save(name='Unreviewed resource', url='https://example.com/unreviewed',
            license='待核对', price='未標明，使用前需核對', status='saved')
        clarified = self.save(name='Different title', url='https://example.com/unreviewed',
            kind='vfx', license='CC0', price='免費', description='Newly checked description',
            previewUrl='https://images.example.com/checked.png')
        self.assertEqual(clarified['item']['name'], first['item']['name'])
        for key, value in {'kind': 'vfx', 'license': 'CC0', 'price': '免費',
                'description': 'Newly checked description', 'previewUrl': 'https://images.example.com/checked.png'}.items():
            self.assertEqual(clarified['item'][key], value)
        self.assertEqual(clarified['item']['status'], 'saved')
        candidate = self.save(name='Candidate', url='https://example.com/candidate', license='待核对')
        checked = self.save(name='Checked candidate', url='https://example.com/candidate',
            kind='model', license='CC Attribution', status='saved')
        self.assertEqual(checked['item']['name'], 'Checked candidate')
        self.assertEqual(checked['item']['license'], 'CC Attribution')
        self.assertEqual(checked['item']['kind'], 'model')
        self.assertEqual(checked['item']['id'], candidate['item']['id'])

    def test_old_revision_and_old_root_cannot_write(self):
        self.save(name='A', url='https://example.com/a', status='saved')
        before = self.store.read_bytes()
        with self.assertRaises(resources.ResourceLibraryConflict):
            self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 0,
                               'name': 'B', 'url': 'https://example.com/b'})
        self.assertEqual(self.store.read_bytes(), before)
        other = self.base / 'other-database'
        other.mkdir()
        self.documents.select(str(other))
        with self.assertRaises(resources.ResourceLibraryConflict):
            self.service.state(expectedRoot=str(self.root))
        with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected network')):
            with self.assertRaises(resources.ResourceLibraryConflict):
                self.search()
        self.assertEqual(list(other.iterdir()), [])
        self.assertEqual(self.store.read_bytes(), before)

    def test_chinese_dictionary_and_polyhaven_literal_matching(self):
        with patch.object(resources, '_fetch_json', return_value=POLYHAVEN) as fetch:
            found = self.search(q='椅子', provider='polyhaven')
            self.assertEqual(found['searchQuery'], 'chair')
            self.assertEqual(found['query'], '椅子')
            self.assertEqual(len(found['items']), 1)
            self.assertEqual(found['items'][0]['url'], 'https://polyhaven.com/a/stone_chair')
            self.assertEqual(found['items'][0]['license'], 'CC0')
            self.assertEqual(fetch.call_args.args[0], 'https://api.polyhaven.com/assets?type=models')
            empty = self.search(q='not-present', provider='polyhaven', kind='texture')
            self.assertEqual(empty['items'], [])
            self.assertFalse(empty['cached'])
            cached_empty = self.search(q='not-present', provider='polyhaven', kind='texture')
            self.assertTrue(cached_empty['cached'])
            self.assertEqual(fetch.call_count, 2)

    def test_provider_errors_are_not_success_or_empty_results(self):
        with patch.object(resources, '_fetch_json', side_effect=resources.ResourceLibraryError('HTTP 429', status=502)):
            with self.assertRaises(resources.ResourceLibraryError) as failed:
                self.search()
            self.assertEqual(failed.exception.status, 502)
        self.assertFalse(self.store.exists())
        with patch.object(resources, '_fetch_json', return_value={'wrong': []}):
            with self.assertRaises(resources.ResourceLibraryError):
                self.search()
        self.assertFalse(self.store.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_existing_store_is_never_overwritten(self):
        self.store.parent.mkdir(parents=True)
        for raw in (b'{broken', b'{"version": 1, "revision": 0, "items": [{}], "searches": []}',
                    b'{"version": 1, "revision": false, "items": [], "searches": []}'):
            self.store.write_bytes(raw)
            with self.assertRaises(resources.ResourceLibraryError):
                self.service.state()
            with self.assertRaises(resources.ResourceLibraryError):
                self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 0,
                                   'name': 'New', 'url': 'https://example.com/new'})
            with patch.object(resources, '_fetch_json', side_effect=AssertionError('unexpected network')):
                with self.assertRaises(resources.ResourceLibraryError):
                    self.search()
            self.assertEqual(self.store.read_bytes(), raw)
            self.assertFalse((self.root / resources.LOCK_RELATIVE).exists())

    def test_corrupt_structured_fields_are_rejected_without_type_errors(self):
        self.save(name='A', url='https://example.com/a')
        original = json.loads(self.store.read_text(encoding='utf-8'))
        for field, invalid in [('status', []), ('kind', {}), ('provenance', 'text')]:
            corrupt = json.loads(json.dumps(original))
            corrupt['items'][0][field] = invalid
            raw = json.dumps(corrupt).encode('utf-8')
            self.store.write_bytes(raw)
            with self.subTest(field=field), self.assertRaises(resources.ResourceLibraryError):
                self.service.state()
            with self.assertRaises(resources.ResourceLibraryError):
                self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 1,
                                   'name': 'B', 'url': 'https://example.com/b'})
            self.assertEqual(self.store.read_bytes(), raw)

    def test_library_symlinks_do_not_escape_or_rewrite_other_files(self):
        outside = self.base / 'outside'
        outside.mkdir()
        escaped = outside / 'library.json'
        escaped.write_text('private data', encoding='utf-8')
        link = self.root / '游戏资源'
        junction = False
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name != 'nt':
                self.skipTest(f'Platform cannot create test symlink: {exc}')
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                self.skipTest('Platform cannot create either a symlink or junction fixture')
            junction = True
        try:
            with self.assertRaises(resources.ResourceLibraryError):
                self.service.state()
            with self.assertRaises(resources.ResourceLibraryError):
                self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 0,
                                   'name': 'New', 'url': 'https://example.com/new'})
            self.assertEqual(escaped.read_text(encoding='utf-8'), 'private data')
            self.assertEqual(sorted(p.name for p in outside.iterdir()), ['library.json'])
        finally:
            link.rmdir() if junction else link.unlink()

    def test_authorization_revoked_during_network_cannot_save(self):
        calls = []
        allowed = [True]
        def authorize():
            calls.append(1)
            if not allowed[0]:
                raise PermissionError('Pairing was revoked')
        def network(url):
            allowed[0] = False
            return SKETCHFAB
        with patch.object(resources, '_fetch_json', side_effect=network):
            with self.assertRaises(PermissionError):
                self.service.search({'expectedRoot': str(self.root), 'q': 'earth'}, authorize=authorize)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.store.exists())
        calls.clear()
        allowed[0] = True
        def revoke_at_write():
            calls.append(1)
            if len(calls) == 2:
                raise PermissionError('Pairing was revoked')
        with self.assertRaises(PermissionError):
            self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 0,
                'name': 'A', 'url': 'https://example.com/a'}, authorize=revoke_at_write)
        self.assertFalse(self.store.exists())

    def test_root_changed_during_network_cannot_write_new_database(self):
        other = self.base / 'other-database'
        other.mkdir()
        def network(url):
            self.documents.select(str(other))
            return SKETCHFAB
        with patch.object(resources, '_fetch_json', side_effect=network):
            with self.assertRaises(resources.ResourceLibraryConflict):
                self.search()
        self.assertEqual(list(other.iterdir()), [])
        self.assertFalse(self.store.exists())

    def test_authorization_runs_outside_document_lock_and_commit_rechecks_revision(self):
        calls = []
        def authorize():
            self.assertFalse(self.documents._lock._is_owned())
            calls.append(1)
            if len(calls) == 2:
                self.save(name='Concurrent', url='https://example.com/concurrent', status='saved')
        with self.assertRaises(resources.ResourceLibraryConflict):
            self.service.save({'expectedRoot': str(self.root), 'expectedRevision': 0,
                'name': 'Stale', 'url': 'https://example.com/stale'}, authorize=authorize)
        state = self.service.state()
        self.assertEqual(state['revision'], 1)
        self.assertEqual([item['name'] for item in state['items']], ['Concurrent'])
        calls.clear()
        def reject_final_search_commit():
            self.assertFalse(self.documents._lock._is_owned())
            calls.append(1)
            if len(calls) == 3:
                raise PermissionError('Revoked just before saving')
        before = self.store.read_bytes()
        with patch.object(resources, '_fetch_json', return_value=SKETCHFAB):
            with self.assertRaises(PermissionError):
                self.service.search({'expectedRoot': str(self.root), 'q': 'earth'}, authorize=reject_final_search_commit)
        self.assertEqual(self.store.read_bytes(), before)

    def test_cross_process_lock_rejects_concurrent_writer(self):
        self.save(name='A', url='https://example.com/a')
        before = self.store.read_bytes()
        lock_path = self.root / resources.LOCK_RELATIVE
        code = """import os,sys
f=open(sys.argv[1],'a+b');f.seek(0)
if os.name=='nt':
 import msvcrt
 msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
else:
 import fcntl
 fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
print('LOCKED',flush=True)
sys.stdin.readline()
f.close()
"""
        child = subprocess.Popen([sys.executable, '-c', code, str(lock_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            self.assertEqual(child.stdout.readline().strip(), 'LOCKED')
            with self.assertRaises(resources.ResourceLibraryConflict):
                self.save(name='B', url='https://example.com/b')
            self.assertEqual(self.store.read_bytes(), before)
        finally:
            child.communicate(input='release\n', timeout=5)

    def test_fixed_transport_timeout_bounded_body_and_http_rate_error(self):
        class Response(io.BytesIO):
            pass
        class Opener:
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return Response(json.dumps(SKETCHFAB).encode('utf-8'))
        opener = Opener()
        with patch.object(resources, 'build_opener', return_value=opener):
            self.assertEqual(resources._fetch_json('https://api.sketchfab.com/v3/search?type=models'), SKETCHFAB)
            self.assertEqual(opener.timeout, resources.SEARCH_TIMEOUT)
            with self.assertRaises(resources.ResourceLibraryError):
                resources._fetch_json('https://example.com/arbitrary')
        with patch.object(resources, 'build_opener') as make:
            make.return_value.open.side_effect = HTTPError('https://api.sketchfab.com/v3/search?', 429, 'Rate limited', {}, None)
            with self.assertRaises(resources.ResourceLibraryError) as failed:
                resources._fetch_json('https://api.sketchfab.com/v3/search?q=test')
            self.assertIn('頻繁', str(failed.exception))
            self.assertEqual(failed.exception.status, 502)
        with patch.object(resources, 'MAX_API_BYTES', 16), patch.object(resources, 'build_opener', return_value=opener):
            with self.assertRaises(resources.ResourceLibraryError):
                resources._fetch_json('https://api.sketchfab.com/v3/search?q=test')

    def test_catalog_network_helpers_restrict_routes_and_bound_html(self):
        class Opener:
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return io.BytesIO(b'<html><body>Official listing</body></html>')
        opener = Opener()
        with patch.object(resources, 'build_opener', return_value=opener):
            for url in ('https://kenney.nl/assets?search=car',
                        'https://kenney.nl/assets/category:3D?search=car',
                        'https://kenney.nl/assets/series:VFX?search=smoke',
                        'https://kenney.nl/assets/category:2D?search=smoke',
                        'https://kenney.nl/assets/category:Textures?search=wood',
                        'https://opengameart.org/art-search-advanced?keys=car'):
                self.assertIn('Official listing', resources._fetch_text(url))
                self.assertEqual(opener.timeout, resources.SEARCH_TIMEOUT)
            for url in ('https://kenney.nl/assets/car-kit', 'https://kenney.nl/redirect?url=https://example.com',
                        'https://kenney.nl.evil.example/assets?search=car',
                        'https://name:secret@kenney.nl/assets?search=car',
                        'https://kenney.nl:443/assets?search=car',
                        'https://opengameart.org/content/car', 'http://kenney.nl/assets?search=car'):
                with self.subTest(url=url), self.assertRaises(resources.ResourceLibraryError):
                    resources._fetch_text(url)
            with patch.object(resources, 'MAX_HTML_BYTES', 8):
                with self.assertRaises(resources.ResourceLibraryError) as failed:
                    resources._fetch_text('https://kenney.nl/assets?search=car')
                self.assertEqual(failed.exception.status, 502)
        with patch.object(resources, 'build_opener') as make:
            make.return_value.open.side_effect = HTTPError('https://kenney.nl/assets?', 429, 'Rate limited', {}, None)
            with self.assertRaises(resources.ResourceLibraryError) as failed:
                resources._fetch_text('https://kenney.nl/assets?search=car')
            self.assertIn('頻繁', str(failed.exception))
        with self.assertRaises(resources.ResourceLibraryError) as failed:
            resources._NoRedirect().redirect_request(None, None, 302, 'Moved', {}, 'https://example.com/')
        self.assertEqual(failed.exception.status, 502)


if __name__ == '__main__':
    unittest.main(verbosity=2)
