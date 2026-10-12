"""Small route checks: exact language/version binding and no write on bad URLs."""
from pathlib import Path
import sys
import unittest
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_room_http import dev_room_get, dev_room_post


class Stub:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def action(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {'method': name, 'path': 'private-image.png', 'mime': 'image/png'}
        return action


class Routes(unittest.TestCase):
    def setUp(self):
        self.room, self.sync = Stub(), Stub()

    def test_localized_state_uses_enriched_current_document(self):
        dev_room_get(self.room, self.sync, 'state', urlencode({'expectedRoot': '中文 库', 'id': 'doc', 'language': 'en'}))
        self.assertEqual(self.sync.calls, [('document_state', ('中文 库', 'doc'), {'language': 'en'})])
        self.assertEqual(self.room.calls, [])

    def test_image_is_bound_to_section_zero_and_exact_language_revision(self):
        query = urlencode({'expectedRoot': '库', 'id': 'doc', 'section': '0', 'revision': 'saved-version', 'language': 'zh'})
        dev_room_get(self.room, self.sync, 'media', query)
        self.assertEqual(self.sync.calls, [('media', ('库', 'doc', 0, 'saved-version'), {'language': 'zh'})])

    def test_extra_duplicate_missing_or_ambiguous_query_never_reaches_service(self):
        queries = ['expectedRoot=x&id=d&id=e', 'id=d', 'expectedRoot=x&path=secret', 'expectedRoot=x&section=-1&id=d&revision=r',
                   'expectedRoot=x&section=01&id=d&revision=r', 'expectedRoot=x&section=0&id=d']
        for query in queries:
            with self.subTest(query=query), self.assertRaises(ValueError):
                dev_room_get(self.room, self.sync, 'media', query)
        self.assertEqual(self.sync.calls, [])

    def test_draft_image_requires_registered_identity_and_saved_version(self):
        values = {'expectedRoot': '库', 'id': 'doc', 'section': '0', 'revision': 'saved-version',
                  'language': 'en', 'stagingName': 'sha.png'}
        dev_room_get(self.room, self.sync, 'media/draft', urlencode(values))
        self.assertEqual(self.sync.calls, [('draft_media', ('库', 'doc', 0, 'saved-version', 'sha.png'), {'language': 'en'})])
        self.sync.calls.clear()
        del values['stagingName']
        with self.assertRaises(ValueError):
            dev_room_get(self.room, self.sync, 'media/draft', urlencode(values))
        with self.assertRaises(ValueError):
            dev_room_get(self.room, self.sync, 'media', urlencode({**values, 'stagingName': 'sha.png'}))
        self.assertEqual(self.sync.calls, [])

    def test_save_uses_the_atomic_content_service_without_a_separate_unlocked_write(self):
        payload = {'expectedRoot': '库', 'id': 'doc', 'language': 'en'}
        result = dev_room_post(self.room, self.sync, 'save', payload)
        self.assertEqual(self.sync.calls, [('save_document', (payload,), {})])
        self.assertEqual(self.room.calls, [])
        self.assertEqual(result['method'], 'save_document')

    def test_upload_never_writes_game_and_receipt_is_explicit(self):
        payload = {'requestId': 'frozen-identity'}
        dev_room_post(self.room, self.sync, 'media/upload', payload)
        self.assertEqual(self.sync.calls[0], ('upload_media', (payload,), {}))
        dev_room_get(self.room, self.sync, 'sync/receipt', 'expectedRoot=x&requestId=r')
        self.assertEqual(self.sync.calls[-1], ('receipt', ('x', 'r'), {}))
        self.assertEqual(self.room.calls, [])

    def test_unknown_routes_are_rejected(self):
        for action in ('../../secret', 'sync/auto', 'media/remove', 'elements/add'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                dev_room_post(self.room, self.sync, action, {})
        self.assertEqual(self.sync.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
