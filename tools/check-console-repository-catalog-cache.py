"""Fast startup/incremental display cache checks; no Git, models or real user data."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console_repository_catalog_cache import RepositoryCatalogCache
from console_repository_publish import catalog_source_identity


class Publisher:
    def __init__(self, root, count=2):
        self.state_dir, self.allowed = root, True
        self.settings = {'repositories': [
            {'id': name, 'path': str(root/name), 'remote': 'origin', 'branch': 'main',
             'versionSources': [{'path': 'version.json', 'kind': 'json', 'key': 'version'}],
             'enabled': True, 'exclude': [], 'syncFiles': []}
            for name in ['slow', 'fast'] + ['more'+str(i) for i in range(count-2)]],
            'naming': {'preset': 'version'}}
        self.block = threading.Event()
        self.started = threading.Event()
        self.calls, self.active, self.maximum = [], 0, 0
        self.guard = threading.Lock()
        self.fail = False

    def _settings(self):
        return deepcopy(self.settings)

    def status(self):
        return {'settings': self._settings(), 'allowed': True, 'busy': False,
                'operation': {'status': 'attention', 'message': 'Live operation remains authoritative'}}

    def version_catalog(self, identifier, *, deadline_seconds=None):
        with self.guard:
            self.calls.append((identifier, deadline_seconds))
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            if identifier == 'slow':
                self.started.set()
                self.block.wait(3)
            if self.fail:
                raise TimeoutError('isolated read timeout')
            return {'repositories': [self.row(identifier, '1.2.3')]}
        finally:
            with self.guard: self.active -= 1

    def row(self, identifier, version):
        repo=next(row for row in self.settings['repositories'] if row['id']==identifier)
        return {'repoId': identifier, 'components': [{'sourceId': 'fixture', 'name': 'Module',
                'currentVersion': version, 'canBump': True}], 'hasChanges': True,
                'sourceIdentity':catalog_source_identity(repo,self.settings['naming']),
                'readState': 'ready', 'message': '',
                'diagnostic': {'severity': 'warning', 'code': 'old_upload_unknown'}}


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='repository-catalog-cache-')
        self.root = Path(self.temp.name)
        self.publisher = Publisher(self.root)
        self.controllers = []
        self.cache = self.create()

    def create(self, **kwargs):
        cache = RepositoryCatalogCache(self.publisher, identity_scope=kwargs.pop('identity_scope', 'owner'), **kwargs)
        self.controllers.append(cache)
        return cache

    def tearDown(self):
        self.publisher.block.set()
        for cache in self.controllers: cache.close()
        self.temp.cleanup()

    def wait(self, predicate):
        end = time.monotonic()+3
        while time.monotonic()<end:
            result = self.cache.snapshot()
            if predicate(result): return result
            time.sleep(.01)
        self.fail('Timed out waiting for isolated reader')

    def test_base_metadata_and_last_known_return_without_any_scan(self):
        self.cache.seed_display([self.publisher.row('slow', '1.2.2')])
        begin = time.monotonic(); data = self.cache.status()
        self.assertLess(time.monotonic()-begin, .2)
        self.assertEqual(self.publisher.calls, [])
        self.assertEqual(data['versionSnapshots'][0]['components'][0]['currentVersion'], '1.2.2')
        self.assertTrue(data['versionSnapshots'][0]['displayOnly'])
        self.assertFalse(data['versionSnapshots'][0]['components'][0]['canBump'])
        self.assertEqual(data['operation']['status'], 'attention')

    def test_slow_repository_does_not_hold_other_rows_or_http(self):
        begin=time.monotonic(); data=self.cache.snapshot(refresh=True)
        self.assertLess(time.monotonic()-begin,.2)
        self.assertFalse(data['complete'])
        data=self.wait(lambda d:d['versionReadStates']['fast']['state']=='ready')
        self.assertEqual(data['versionReadStates']['slow']['state'],'reading')
        self.assertEqual(data['versionSnapshots'][0]['repoId'],'fast')
        self.assertFalse(data['versionSnapshots'][0]['displayOnly'])
        self.assertEqual(self.publisher.calls[0][1],30)

    def test_refresh_and_poll_deduplicate_and_bound_workers(self):
        self.publisher.settings=Publisher(self.root,8).settings
        for _ in range(20): self.cache.snapshot(refresh=True)
        self.wait(lambda d:d['versionReadStates']['more5']['state']=='ready')
        for _ in range(20): self.cache.snapshot()
        self.assertLessEqual(self.publisher.maximum,2)
        self.assertEqual(len(self.publisher.calls),8)

    def test_timeout_keeps_previous_values_and_disables_mutation(self):
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        self.publisher.fail=True
        self.cache.snapshot('fast',refresh=True)
        data=self.wait(lambda d:d['versionReadStates']['fast']['state']=='error')
        self.assertEqual(data['versionSnapshots'][0]['components'][0]['currentVersion'],'1.2.2')
        self.assertTrue(data['versionSnapshots'][0]['displayOnly'])
        self.assertFalse(data['versionSnapshots'][0]['components'][0]['canBump'])

    def test_destination_and_full_configuration_change_invalidate_display(self):
        for field,value in [('path','changed'),('branch','work'),('exclude',['private/']),
                            ('syncFiles',[{'source':'saved','target':'work'}]),('versionSources',[])]:
            self.cache.seed_display([self.publisher.row('fast','1.2.2')])
            row=self.publisher.settings['repositories'][1]
            previous=deepcopy(row[field]); row[field]=value
            self.assertEqual(self.cache.status()['versionSnapshots'],[])
            row[field]=previous
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        self.publisher.settings['naming']['preset']='module_version'
        self.assertEqual(self.cache.status()['versionSnapshots'],[])

    def test_old_target_late_result_never_populates_new_target(self):
        self.cache.snapshot('slow',refresh=True)
        self.assertTrue(self.publisher.started.wait(1))
        self.publisher.settings['repositories'][0]['branch']='new-work'
        self.cache.status()
        self.publisher.block.set()
        time.sleep(.1)
        self.assertEqual(self.cache.snapshot('slow')['versionSnapshots'],[])
        self.assertEqual(self.cache.snapshot('slow')['versionReadStates']['slow']['state'],'idle')

    def test_restart_reuses_display_only_and_owner_change_clears_it(self):
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        restarted=self.create()
        self.assertTrue(restarted.status()['versionSnapshots'][0]['displayOnly'])
        other=self.create(identity_scope='another-owner')
        self.assertEqual(other.status()['versionSnapshots'],[])

    def test_broken_cache_cannot_block_base_metadata(self):
        self.cache.path.write_text('{broken',encoding='utf-8')
        restarted=self.create()
        self.assertEqual(restarted.status()['versionSnapshots'],[])
        self.assertEqual(self.publisher.calls,[])

    def test_display_migration_keeps_actual_original_checked_time(self):
        observed='2026-10-14T12:30:00+00:00'
        self.cache.seed_display([self.publisher.row('fast','1.2.2')],checked_at=observed)
        data=self.cache.status()
        self.assertEqual(data['versionSnapshots'][0]['checkedAt'],observed)
        self.assertTrue(data['versionSnapshots'][0]['displayOnly'])

    def test_disabled_repository_is_not_scanned_by_all_refresh(self):
        self.publisher.settings['repositories'][0]['enabled']=False
        self.cache.snapshot(refresh=True)
        self.wait(lambda d:d['complete'])
        self.assertEqual([row[0] for row in self.publisher.calls],['fast'])
        self.cache.snapshot('slow',refresh=True)
        self.assertTrue(self.publisher.started.wait(1))

    def test_informative_fallback_and_sync_messages_update_normally(self):
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        row=self.publisher.row('fast','1.2.3')
        row.update(message='Use remembered fallback title',
                   diagnostic={'severity':'info','code':'version_fallback'})
        self.publisher.version_catalog=lambda *a,**kw:{'repositories':[row]}
        self.cache.snapshot('fast',refresh=True)
        data=self.wait(lambda d:d['complete'])
        self.assertEqual(data['versionReadStates']['fast']['state'],'ready')
        self.assertEqual(data['versionSnapshots'][0]['components'][0]['currentVersion'],'1.2.3')

    def test_catalog_read_error_keeps_previous_value(self):
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        row=self.publisher.row('fast','1.2.3');row.update(readState='error',message='Repository source missing',
            diagnostic={'code':'repo_missing','category':'repository','severity':'error',
                        'summary':'Repository source missing','target':{'section':'connection','field':'path'}})
        self.publisher.version_catalog=lambda *a,**kw:{'repositories':[row]}
        self.cache.snapshot('fast',refresh=True)
        data=self.wait(lambda d:d['complete'])
        self.assertEqual(data['versionReadStates']['fast']['state'],'error')
        self.assertEqual(data['versionReadStates']['fast']['diagnostic']['code'],'repo_missing')
        self.assertEqual(data['versionSnapshots'][0]['components'][0]['currentVersion'],'1.2.2')

    def test_target_aba_does_not_accept_different_actual_read_source(self):
        self.cache.seed_display([self.publisher.row('fast','1.2.2')])
        def read_other_target(*a,**kw):
            row=self.publisher.settings['repositories'][1]
            row['branch']='temporary-target'
            result=self.publisher.row('fast','9.9.9')
            row['branch']='main'
            return {'repositories':[result]}
        self.publisher.version_catalog=read_other_target
        self.cache.snapshot('fast',refresh=True)
        data=self.wait(lambda d:d['complete'])
        self.assertEqual(data['versionReadStates']['fast']['state'],'error')
        self.assertEqual(data['versionSnapshots'][0]['components'][0]['currentVersion'],'1.2.2')
        self.assertTrue(data['versionSnapshots'][0]['displayOnly'])

    def test_worker_start_failure_is_visible_and_retry_recovers(self):
        with patch('console_repository_catalog_cache.threading.Thread.start',side_effect=RuntimeError('no slot')):
            data=self.cache.snapshot('fast',refresh=True)
        self.assertTrue(data['complete'])
        self.assertEqual(data['versionReadStates']['fast']['state'],'error')
        self.assertEqual(len(self.cache._threads),0)
        self.cache.snapshot('fast',refresh=True)
        self.wait(lambda d:d['versionReadStates']['fast']['state']=='ready')

    def test_failed_cache_cleanup_cannot_kill_reader(self):
        original=Path.unlink
        def fail_temporary(path,*a,**kw):
            if path.name.startswith('catalog-display-cache.json.'):
                raise PermissionError('isolated filesystem cleanup failure')
            return original(path,*a,**kw)
        with patch('console_repository_catalog_cache.os.replace',side_effect=PermissionError('no replace')), \
             patch('console_repository_catalog_cache.Path.unlink',new=fail_temporary):
            self.cache.snapshot('fast',refresh=True)
            self.wait(lambda d:d['versionReadStates']['fast']['state']=='ready')
        self.assertTrue(all(thread.is_alive() for thread in self.cache._threads))


if __name__=='__main__': unittest.main()
