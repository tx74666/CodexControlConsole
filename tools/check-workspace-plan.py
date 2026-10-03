import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_plan import (
    MAX_PLAN_BYTES, MAX_PLAN_STATE_BYTES, PlanStateConflict,
    normalize_plan, normalize_actual_plan, plan_script, read_plan,
    read_plan_state, read_actual_plan, save_plan_state,
)


def sample():
    return {'version': 1, 'revision': 'plan-test-v1', 'groups': [
        {'id': f'group-{index}', 'title': f'Group {index}', 'summary': 'Goal',
         'items': [{'id': f'first-{index}', 'text': 'Do the next step', 'done': False}]} for index in range(4)]}


class PlanChecks(unittest.TestCase):
    def test_missing_plan_is_empty_and_reading_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_plan(directory), {'plan': None, 'error': ''})
            path = Path(directory) / 'workspace-plan.json'
            raw = json.dumps(sample(), indent=4).encode()
            path.write_bytes(raw)
            self.assertEqual(read_plan(directory)['plan'], sample())
            self.assertEqual(path.read_bytes(), raw)
            value = sample()
            value['groups'][0]['items'] = []
            self.assertEqual(normalize_plan(value)['groups'][0]['items'], [])

    def test_invalid_config_returns_no_plan_and_never_changes_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workspace-plan.json'
            for raw in [b'{bad', b'\xff', b'{}', b' ' * (MAX_PLAN_BYTES + 1)]:
                path.write_bytes(raw)
                self.assertIsNone(read_plan(directory)['plan'])
                self.assertTrue(read_plan(directory)['error'])
                self.assertEqual(path.read_bytes(), raw)
            with patch('workspace_plan.Path.open', side_effect=PermissionError('denied')):
                self.assertIsNone(read_plan(directory)['plan'])

    def test_duplicate_ids_wrong_types_and_limits_are_rejected(self):
        for mutate in [lambda p: p.update(version=True), lambda p: p.update(revision='bad\nrevision'),
                       lambda p: p['groups'].pop(), lambda p: p['groups'][1].update(id='group-0'),
                       lambda p: p['groups'][0]['items'].append(copy.deepcopy(p['groups'][0]['items'][0])),
                       lambda p: p['groups'][1]['items'][0].update(id='first-0'),
                       lambda p: p['groups'][0]['items'][0].update(done='false'),
                       lambda p: p['groups'][0]['items'][0].update(text='x' * 501)]:
            value = sample()
            mutate(value)
            with self.assertRaises(ValueError):
                normalize_plan(value)

    def test_javascript_payload_is_inert_and_routes_require_local_trusted_requests(self):
        value = sample()
        value['groups'][0]['title'] = '</script><script>alert(1)</script>\u2028'
        body = plan_script({'plan': normalize_plan(value), 'error': ''}).decode()
        self.assertNotIn('<', body)
        self.assertNotIn('\u2028', body)
        encoded = body.split('window.CODEX_WORKSPACE_PLAN=', 1)[1].split(';\n', 1)[0]
        self.assertEqual(json.loads(encoded), normalize_plan(value))
        # Import-time initialization must stay inside this test's disposable data directory.
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'CODEX_CONTROL_DATA_DIR': directory,
            'CODEX_CONTROL_EDITION': 'public',
            'CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR': str(Path(directory) / 'desktop'),
            'CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT': str(Path(directory) / 'desktop/current.json'),
            'CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE': str(Path(directory) / 'Startup/Disabled.vbs'),
        }):
            (Path(directory) / '.cache-migrated-v0.3').write_text('isolated test', encoding='utf-8')
            import world_console
            self.assertEqual(world_console.USER_DATA_DIR, Path(directory).resolve())
        class Handler:
            path = '/api/workspace-plan.js'
            allow_local = True
            allow_trusted = True
            output = None
            def _private_phone_path(self): return False  # API-only route fixture, no static files.
            def require_local_request(self): return self.allow_local
            def require_trusted_post_context(self): return self.allow_trusted
            def send_bytes_response(self, body, mime): self.output = (body, mime)
            def send_json(self, payload): self.output = payload
        with patch.object(world_console, 'read_workspace_plan', return_value={'plan': sample(), 'error': ''}) as read:
            handler = Handler()
            handler.allow_local = False
            world_console.ConsoleHandler.do_GET(handler)
            read.assert_not_called()
            handler.allow_local, handler.allow_trusted = True, False
            world_console.ConsoleHandler.do_GET(handler)
            read.assert_not_called()
            handler.allow_trusted = True
            world_console.ConsoleHandler.do_GET(handler)
            self.assertEqual(handler.output[1], 'application/javascript; charset=utf-8')
            handler.path = '/api/workspace-plan'
            world_console.ConsoleHandler.do_GET(handler)
            self.assertEqual(handler.output['plan']['revision'], 'plan-test-v1')


class SavedPlanChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.seed_path = self.directory / 'workspace-plan.json'
        self.state_path = self.directory / 'workspace-plan-state.json'
        self.seed_path.write_text(json.dumps(sample(), indent=4), encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def test_existing_browser_tasks_and_progress_are_saved_without_rewriting_seed(self):
        original = self.seed_path.read_bytes()
        self.assertFalse(read_plan_state(self.directory)['persisted'])
        self.assertEqual(read_actual_plan(self.directory)['plan'], sample())
        value = sample()
        value['groups'][0]['items'][0]['done'] = True
        value['groups'][1]['items'] = []
        value['groups'][2]['items'].append({'id': 'custom', 'text': 'A custom detail', 'done': True})
        saved = save_plan_state(self.directory, value, None)
        self.assertTrue(saved['actualDone'])
        self.assertEqual(read_actual_plan(self.directory)['plan'], value)
        self.assertEqual(self.seed_path.read_bytes(), original)
        self.assertEqual(save_plan_state(self.directory, value, saved['hash'])['updatedAt'], saved['updatedAt'])
        self.assertEqual(save_plan_state(self.directory, value, None)['hash'], saved['hash'], 'a lost successful response can be retried')

    def test_stale_plan_cannot_overwrite_a_more_recent_snapshot(self):
        first = save_plan_state(self.directory, sample(), None)
        newer = sample()
        newer['groups'][0]['items'][0]['done'] = True
        second = save_plan_state(self.directory, newer, first['hash'])
        old_bytes = self.state_path.read_bytes()
        with self.assertRaises(PlanStateConflict):
            save_plan_state(self.directory, sample(), first['hash'])
        self.assertNotEqual(first['hash'], second['hash'])
        self.assertEqual(self.state_path.read_bytes(), old_bytes)

    def test_broken_state_never_falls_back_to_the_seed_or_gets_overwritten(self):
        for raw in [b'{bad', b'\xff', b'{}', b' ' * (MAX_PLAN_STATE_BYTES + 1)]:
            self.state_path.write_bytes(raw)
            result = read_actual_plan(self.directory)
            self.assertIsNone(result['plan'])
            self.assertTrue(result['error'])
            with self.assertRaises((ValueError, UnicodeError)):
                save_plan_state(self.directory, sample(), None)
            self.assertEqual(self.state_path.read_bytes(), raw)

    def test_invalid_tasks_or_failed_atomic_replace_keep_the_saved_snapshot(self):
        saved = save_plan_state(self.directory, sample(), None)
        old_bytes = self.state_path.read_bytes()
        invalid = sample()
        invalid['groups'][0]['items'][0]['text'] = 'x' * 501
        with self.assertRaises(ValueError):
            save_plan_state(self.directory, invalid, saved['hash'])
        oversized = sample()
        for index, group in enumerate(oversized['groups']):
            group['items'] = [{'id': f'large-{index}-{item}', 'text': '\u4e2d' * 500, 'done': False} for item in range(75)]
        with self.assertRaises(ValueError):
            save_plan_state(self.directory, oversized, saved['hash'])
        newer = sample()
        newer['groups'][0]['items'][0]['done'] = True
        with patch('workspace_plan.os.replace', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                save_plan_state(self.directory, newer, saved['hash'])
        self.assertEqual(self.state_path.read_bytes(), old_bytes)
        self.assertEqual(list(self.directory.glob('.workspace-plan-state.*.tmp')), [])

    def test_seed_updates_merge_custom_details_completion_and_deletions(self):
        value = sample()
        value['groups'][0]['items'][0]['done'] = True
        value['groups'][1]['items'] = []
        value['groups'][2]['items'].append({'id': 'custom', 'text': 'Keep this detail', 'done': False})
        original = save_plan_state(self.directory, value, None)
        updated = sample()
        updated['revision'] = 'plan-test-v2'
        updated['groups'][0]['items'][0]['text'] = 'An updated step'
        updated['groups'][1]['items'][0]['text'] = 'Do not resurrect this deleted step'
        updated['groups'][2]['items'].append({'id': 'added', 'text': 'New step', 'done': False})
        updated['groups'][3]['items'][0]['done'] = True
        raw = json.dumps(updated).encode()
        self.seed_path.write_bytes(raw)
        current = read_actual_plan(self.directory)
        self.assertTrue(current['actualDone'])
        self.assertNotEqual(current['hash'], original['hash'])
        self.assertEqual(current['plan']['groups'][0]['items'][0], {'id': 'first-0', 'text': 'An updated step', 'done': True})
        self.assertEqual(current['plan']['groups'][1]['items'], [])
        self.assertEqual([item['id'] for item in current['plan']['groups'][2]['items']], ['first-2', 'custom', 'added'])
        self.assertTrue(current['plan']['groups'][3]['items'][0]['done'])
        self.assertEqual(self.seed_path.read_bytes(), raw)

    def test_unsafe_seed_identifier_changes_or_bad_seed_preserve_saved_bytes(self):
        saved = save_plan_state(self.directory, sample(), None)
        old_bytes = self.state_path.read_bytes()
        changed = sample()
        moved = changed['groups'][0]['items'].pop()
        changed['groups'][1]['items'].append(moved)
        self.seed_path.write_text(json.dumps(changed), encoding='utf-8')
        self.assertTrue(read_actual_plan(self.directory)['error'])
        self.assertEqual(self.state_path.read_bytes(), old_bytes)
        self.seed_path.write_bytes(b'{bad')
        self.assertTrue(read_actual_plan(self.directory)['error'])
        with self.assertRaises(ValueError):
            save_plan_state(self.directory, sample(), saved['hash'])
        self.assertEqual(self.state_path.read_bytes(), old_bytes)

    def test_public_users_without_a_seed_can_preserve_six_existing_groups(self):
        self.seed_path.unlink()
        value = sample()
        value['revision'] = 'local-plan-v1'
        value['groups'].extend({'id': f'public-{index}', 'title': f'Public {index}', 'summary': '',
                                'items': [{'id': f'custom-{index}', 'text': 'Existing public task', 'done': True}]} for index in (5, 6))
        saved = save_plan_state(self.directory, value, None)
        self.assertIsNone(saved['seedRevision'])
        self.assertEqual(len(read_actual_plan(self.directory)['plan']['groups']), 6)
        self.assertEqual(normalize_actual_plan(value), value)
        with self.assertRaises(ValueError):
            normalize_plan(value)
        value['groups'] *= 3
        with self.assertRaises(ValueError):
            normalize_actual_plan(value)

    def test_concurrent_different_clients_have_only_one_successful_write(self):
        initial = save_plan_state(self.directory, sample(), None)
        def update(index):
            value = sample()
            value['groups'][index]['items'][0]['done'] = True
            try:
                save_plan_state(self.directory, value, initial['hash'])
                return 'saved'
            except PlanStateConflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(update, (0, 1))), ['saved', 'conflict'])
        self.assertEqual(sum(item['done'] for group in read_actual_plan(self.directory)['plan']['groups'] for item in group['items']), 1)

    def test_state_routes_enforce_local_trusted_context_and_request_contract(self):
        import world_console
        class Handler:
            path = '/api/workspace-plan/state'
            allow_local = True
            allow_trusted = True
            output = None
            body = {'plan': sample(), 'expectedHash': None}
            limit = None
            def _private_phone_path(self): return False  # API-only route fixture, no static files.
            def require_local_request(self): return self.allow_local
            def require_trusted_post_context(self): return self.allow_trusted
            def send_json(self, payload, status=200): self.output = (payload, status)
            def read_json_body(self, max_bytes=None): self.limit = max_bytes; return self.body
        with patch.object(world_console, 'USER_DATA_DIR', self.directory):
            handler = Handler()
            for local, trusted in ((False, True), (True, False)):
                handler.allow_local, handler.allow_trusted = local, trusted
                world_console.ConsoleHandler.do_GET(handler)
                world_console.ConsoleHandler._dispatch_POST(handler)
                self.assertIsNone(handler.output)
                self.assertFalse(self.state_path.exists())
            handler.allow_local = handler.allow_trusted = True
            world_console.ConsoleHandler._dispatch_POST(handler)
            self.assertEqual(handler.output[1], 200)
            self.assertEqual(handler.limit, MAX_PLAN_BYTES + 1024)
            handler.body = {**handler.body, 'extra': 'not allowed'}
            world_console.ConsoleHandler._dispatch_POST(handler)
            self.assertEqual(handler.output[1], 400)
            world_console.ConsoleHandler.do_GET(handler)
            self.assertTrue(handler.output[0]['actualDone'])
            newer = sample()
            newer['groups'][0]['items'][0]['done'] = True
            save_plan_state(self.directory, newer, handler.output[0]['hash'])
            handler.body = {'plan': sample(), 'expectedHash': None}
            world_console.ConsoleHandler._dispatch_POST(handler)
            self.assertEqual(handler.output[1], 409)


if __name__ == '__main__':
    unittest.main()
