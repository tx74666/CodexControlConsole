"""Disposable checks for transfer schema readiness and wallpaper atomic writes."""
import ast
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import transfer_store as transfer

class BackendChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='console-backend-check-')
        self.root = Path(self.tmp.name)
        self.selected = ''
        self.store = transfer.TransferStore(lambda: self.selected, self.root / 'fallback')

    def tearDown(self):
        self.tmp.cleanup()

    def database(self):
        return self.store._location()[1] / 'history.sqlite3'

    def test_cached_reads_do_not_require_a_sqlite_write_lock(self):
        before = self.store.list()
        database = self.database()
        actual_connect = sqlite3.connect
        with closing(actual_connect(database)) as writer, writer:
            writer.execute('BEGIN IMMEDIATE')
            def connect(*args, **kwargs):
                kwargs['timeout'] = 0.1
                return actual_connect(*args, **kwargs)
            with patch.object(transfer.sqlite3, 'connect', side_effect=connect):
                after = self.store.list('revision=' + before['revision'])
            self.assertTrue(after['unchanged'])
            writer.rollback()

    def test_external_schema_change_is_repaired(self):
        self.store.list()
        database = self.database()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('DROP INDEX attachment_messages')
        self.store.list()
        with closing(sqlite3.connect(database)) as db, db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='attachment_messages'").fetchone())

    def test_replacement_with_same_schema_generation_is_initialized(self):
        self.store.list()
        database = self.database()
        with closing(sqlite3.connect(database)) as db, db:
            version = db.execute('PRAGMA schema_version').fetchone()[0]
        replacement = self.root / 'replacement.sqlite3'
        with closing(sqlite3.connect(replacement)) as db, db:
            db.execute('PRAGMA schema_version=' + str(version))
        os.replace(replacement, database)
        self.assertEqual(self.store.list()['messages'], [])
        with closing(sqlite3.connect(database)) as db, db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='messages'").fetchone())

    def test_selected_database_changes_and_returns_are_checked(self):
        self.store.list()
        first = self.database()
        library = self.root / 'other-library'
        library.mkdir()
        self.selected = str(library)
        self.assertEqual(self.store.list()['messages'], [])
        self.assertNotEqual(first, self.database())
        self.selected = ''
        self.assertEqual(self.store.list()['messages'], [])

    def test_failed_initialization_is_not_cached_and_can_retry(self):
        class FailingConnection(sqlite3.Connection):
            def executescript(self, sql):
                raise sqlite3.OperationalError('isolated schema failure')
        actual_connect = sqlite3.connect
        def connect(*args, **kwargs):
            kwargs['factory'] = FailingConnection
            return actual_connect(*args, **kwargs)
        with patch.object(transfer.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.list()
        self.assertIsNone(self.store._schema_key)
        self.assertEqual(self.store.list()['messages'], [])
        self.assertIsNotNone(self.store._schema_key)

    def test_same_instance_concurrent_reads_initialize_once(self):
        migrations = []
        class TrackedConnection(sqlite3.Connection):
            def executescript(self, sql):
                migrations.append(sql)
                return super().executescript(sql)
        actual_connect = sqlite3.connect
        def connect(*args, **kwargs):
            kwargs['factory'] = TrackedConnection
            return actual_connect(*args, **kwargs)
        with patch.object(transfer.sqlite3, 'connect', side_effect=connect):
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: self.store.list(), range(12)))
        self.assertEqual(len(migrations), 1)
        self.assertTrue(all(item['messages'] == [] for item in results))

    def test_legacy_star_migration_preserves_history(self):
        database = self.database()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE messages (id TEXT PRIMARY KEY,request_id TEXT NOT NULL,sender TEXT NOT NULL,created_at TEXT NOT NULL,text TEXT NOT NULL,fingerprint TEXT NOT NULL,UNIQUE(sender,request_id))')
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', ('a' * 32, 'legacy', 'desktop', '2026-10-01', 'kept original', 'saved'))
        messages = self.store.list()['messages']
        self.assertEqual(messages[0]['text'], 'kept original')
        self.assertFalse(messages[0]['starred'])

    def wallpaper_functions(self):
        # Extract pure helpers to avoid starting/importing the desktop application.
        names = {'atomic_write_json', 'write_wallpaper_order', 'write_original_wallpaper_record', 'capture_original_wallpaper'}
        source = ast.parse((REPO / 'world_console.py').read_text(encoding='utf-8-sig'))
        nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in nodes}, names)
        order = self.root / 'wallpaper_order.json'
        original = self.root / 'original_wallpaper.json'
        env = {'Path': Path, 'os': os, 'tempfile': tempfile, 'json': json, 'shutil': shutil,
               'datetime': datetime, 'timezone': timezone, 'WALLPAPER_ORDER_FILE': order,
               'ORIGINAL_WALLPAPER_RECORD': original, 'sanitize_string_list': lambda value: value or [],
               'scan_wallpapers': lambda: [{'path': 'one.png'}, {'path': 'two.png'}],
               'list_wallpapers': lambda: [{'path': item} for item in json.loads(order.read_text())['order']],
               'get_windows_wallpaper_style': lambda: {'name': 'fit'}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'isolated-wallpaper', 'exec'), env)
        return env

    def test_all_three_wallpaper_save_paths_preserve_formal_file_on_replace_failure(self):
        env = self.wallpaper_functions()
        source = self.root / 'source.png'
        source.write_bytes(b'isolated original image')
        original = env['ORIGINAL_WALLPAPER_RECORD']
        order = env['WALLPAPER_ORDER_FILE']
        original.write_text('{"path":"kept"}', encoding='utf-8')
        order.write_text('{"order":["two.png","one.png"]}', encoding='utf-8')
        env['original_wallpaper_state'] = lambda: {'saved': True, 'style': {}}
        env['read_original_wallpaper_record'] = lambda: {'path': 'kept'}
        calls = [lambda: env['write_wallpaper_order']({'order': ['one.png']}),
                 lambda: env['write_original_wallpaper_record'](source),
                 lambda: env['capture_original_wallpaper']()]
        for call in calls:
            prior = (original.read_bytes(), order.read_bytes())
            with patch.object(os, 'replace', side_effect=OSError('isolated replace failure')):
                with self.assertRaises(OSError):
                    call()
            self.assertEqual((original.read_bytes(), order.read_bytes()), prior)
            self.assertEqual(list(self.root.glob('.*.tmp')), [])
        env['write_wallpaper_order']({'order': ['one.png']})
        self.assertEqual(json.loads(order.read_text())['order'], ['one.png', 'two.png'])
        env['write_original_wallpaper_record'](source)
        self.assertEqual(json.loads(original.read_text())['path'], str(source))

    def test_unloaded_music_snapshot_cannot_clear_a_valid_saved_selection(self):
        source = ast.parse((REPO / 'world_console.py').read_text(encoding='utf-8-sig'))
        node = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'write_music_state')
        music = self.root / 'music'
        music.mkdir()
        track = music / 'kept.mp3'
        track.write_bytes(b'fixture')
        saved = {'selectedTrackPath': 'kept.mp3', 'order': ['kept.mp3'], 'tiers': {'kept.mp3': 'first'}}
        writes = []
        env = {'MUSIC_DIR': music, 'MUSIC_EXTENSIONS': {'.mp3'}, 'MUSIC_STATE_LOCK': threading.RLock(),
               'read_music_state': lambda: dict(saved), 'sanitize_state_path': lambda value: str(value or ''),
               'is_path_inside': lambda path, root: path.is_relative_to(root),
               'store_music_state': lambda value, previous: writes.append(value)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'isolated-music-state', 'exec'), env)
        write = env['write_music_state']
        result = write({'selectedTrackPath': ''})
        self.assertTrue(result['staleClient'])
        self.assertEqual(result['state'], saved)
        self.assertEqual(writes, [])
        with patch.object(Path, 'stat', side_effect=PermissionError('fixture unavailable')):
            self.assertEqual(write({'selectedTrackPath': ''})['state'], saved)
        self.assertEqual(writes, [])
        self.assertTrue(write({'selectedTrackPath': 'kept.mp3'})['ok'])
        self.assertEqual(writes, [], 'An unchanged snapshot must not rotate the previous-state file')
        saved['selectedTrackPath'] = '../outside.mp3'
        self.assertTrue(write({'selectedTrackPath': ''})['staleClient'])
        self.assertEqual(writes, [])
        saved['selectedTrackPath'] = 'kept.mp3'
        track.unlink()
        result = write({'selectedTrackPath': ''})
        self.assertTrue(result['ok'])
        self.assertEqual(result['state']['selectedTrackPath'], '')
        self.assertEqual(writes[-1]['order'], saved['order'])

if __name__ == '__main__':
    sys.argv = [sys.argv[0]]
    unittest.main(verbosity=2)
