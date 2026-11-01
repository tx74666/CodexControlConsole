"""Bounded local discovery scheduling, using disposable roots and fake commits."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import image_manager
from image_manager_watch import ImageFolderWatch


class Config:
    def __init__(self, root):
        self.reads=0
        self.value={'root':str(root),'rootIdentity':image_manager._identity(root),
                    'deviceRoot':'Z:/must-never-be-probed'}
    def _config(self):
        self.reads+=1
        return copy.deepcopy(self.value)


class Inventory:
    def __init__(self):self.value='first';self.reads=0
    def __call__(self,root):
        self.reads+=1
        return {'inventory':[{'path':'Image.png','size':1,'mtimeNs':self.value,'device':'1','inode':'1','nlink':1}],
                'inventoryToken':hashlib.sha256(self.value.encode()).hexdigest()}


class Checks(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='console-image-watch-')
        self.directory=Path(self.temporary.name).resolve()
        self.root=self.directory/'library';self.root.mkdir()
        self.service,self.inventory=Config(self.root),Inventory()
        self.calls,self.watches=[],[]
    def tearDown(self):
        for watch in self.watches:watch.close()
        self.assertEqual(self.root.parent,self.directory)
        self.temporary.cleanup()
    def watch(self,callback=None,**kwargs):
        def commit(payload):
            self.calls.append(payload)
            return {'root':str(self.root),'status':'noop','localRevision':'revision-1'}
        value=ImageFolderWatch(self.service,callback or commit,inventory_reader=self.inventory,
                               wall_clock=lambda:'fixture-time',**kwargs)
        self.watches.append(value)
        return value

    def test_constructor_status_and_poke_are_cached_and_start_no_work(self):
        watch=self.watch()
        self.assertEqual(watch.status(str(self.root))['reason'],'root_pending')
        watch.poke()
        self.assertEqual((self.service.reads,self.inventory.reads,self.calls),(0,0,[]))
        self.assertIsNone(watch._thread)
        self.assertFalse(watch.busy)
        self.assertFalse(watch.stopping)
        watch.close();watch.close()
        self.assertTrue(watch.stopping)
        self.assertEqual((self.service.reads,self.inventory.reads),(0,0))

    def test_cold_start_needs_two_stable_observations_and_acknowledgement(self):
        watch=self.watch()
        first=watch.tick(0)
        self.assertEqual((first['status'],first['pending']),('settling',True))
        self.assertIsNone(first['lastIndexedAt'])
        self.assertTrue(first['changeToken'])
        watch.tick(1)
        self.assertEqual(self.calls,[])
        result=watch.tick(2)
        self.assertFalse(result['pending'])
        self.assertEqual(result['lastIndexedAt'],'fixture-time')
        self.assertEqual(result['localRevision'],'revision-1')
        self.assertEqual(len(self.calls),1)
        self.assertEqual(set(self.calls[0]),{'expectedRoot','inventoryToken','inventory'})
        version=result['statusRevision']
        watch.tick(10)
        self.assertEqual((len(self.calls),watch.status()['statusRevision']),(1,version))

    def test_partial_copy_signature_changes_reset_settle_without_decoding(self):
        watch=self.watch()
        watch.tick(0)
        self.inventory.value='copying'
        watch.tick(1);watch.tick(2)
        self.assertEqual(self.calls,[])
        self.inventory.value='complete'
        watch.tick(3);watch.tick(4)
        self.assertEqual(self.calls,[])
        watch.tick(5)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0]['inventoryToken'],hashlib.sha256(b'complete').hexdigest())

    def test_busy_deferral_never_credits_observation_as_indexed_and_retries_after_delay(self):
        attempts=[]
        def callback(payload):
            attempts.append(payload)
            return {'status':'deferred','reason':'notion_pending'} if len(attempts)==1 else {'status':'updated','localRevision':'new'}
        watch=self.watch(callback)
        watch.tick(0);deferred=watch.tick(2)
        self.assertEqual((deferred['status'],deferred['pending']),('deferred',True))
        self.assertIsNone(deferred['lastIndexedAt'])
        watch.tick(3);watch.tick(6)
        self.assertEqual(len(attempts),1)
        refreshed=watch.tick(7)
        self.assertEqual((refreshed['status'],refreshed['pending']),('changed',False))
        self.assertEqual(len(attempts),2)

    def test_failed_refresh_backs_off_but_new_file_signature_can_retry_after_settling(self):
        attempts=[]
        def callback(payload):
            attempts.append(payload)
            if len(attempts)<3:raise ValueError('not a public error message')
            return {'status':'noop'}
        watch=self.watch(callback)
        watch.tick(0);watch.tick(2);watch.tick(3)
        self.assertEqual(len(attempts),1)
        watch.tick(7);watch.tick(8)
        self.assertEqual(len(attempts),2)
        self.inventory.value='fixed-copy'
        watch.tick(9);watch.tick(11)
        self.assertEqual(len(attempts),3)
        self.assertFalse(watch.status()['pending'])

    def test_root_rebind_never_reuses_previous_root_acknowledgement(self):
        watch=self.watch();watch.tick(0);watch.tick(2)
        other=self.directory/'other';other.mkdir()
        self.service.value.update(root=str(other),rootIdentity=image_manager._identity(other))
        pending=watch.tick(3)
        self.assertEqual((pending['root'],pending['pending']),(str(other),True))
        self.assertIsNone(pending['lastIndexedAt'])
        self.assertEqual(len(self.calls),1)
        # The returned root is checked too, so a stale callback cannot credit it.
        failed=watch.tick(5)
        self.assertTrue(failed['pending'])
        self.assertIsNone(failed['lastIndexedAt'])
        self.assertEqual(watch.status(str(self.root))['reason'],'root_pending')

    def test_reparse_or_replaced_root_never_reaches_inventory_or_callback(self):
        watch=self.watch()
        with patch.object(image_manager,'_link',return_value=True):
            self.assertEqual(watch.tick(0)['status'],'error')
        self.assertEqual((self.inventory.reads,self.calls),(0,[]))
        old=self.directory/'old-root'
        self.root.rename(old);self.root.mkdir()
        self.assertEqual(watch.tick(10)['status'],'error')
        self.assertEqual((self.inventory.reads,self.calls),(0,[]))

    def test_inventory_overflow_and_invalid_callback_remain_pending(self):
        def overflow(root):
            error=image_manager.ImageManagerError('Private diagnostic must not be exposed')
            error.code='inventory_limit'
            raise error
        watch=self.watch();watch.inventory_reader=overflow
        result=watch.tick(0)
        self.assertEqual((result['status'],result['reason']),('error','inventory_limit'))
        self.assertTrue(result['pending'])
        self.assertIsNone(result['changeToken'])
        self.assertEqual(self.calls,[])
        watch=self.watch(lambda payload: {'status':'completed'})
        watch.tick(0)
        self.assertEqual(watch.tick(2)['status'],'error')
        self.assertTrue(watch.status()['pending'])

    def test_close_during_own_slow_callback_is_bounded_and_does_not_credit_late_result(self):
        entered,release=threading.Event(),threading.Event()
        def callback(payload):
            entered.set();release.wait(3)
            return {'status':'updated','localRevision':'too-late'}
        watch=self.watch(callback,interval=.05,settle=0,join_timeout=.05)
        watch.start();watch.start()
        self.assertTrue(entered.wait(2))
        self.assertTrue(watch.busy)
        started=time.monotonic();watch.close()
        self.assertLess(time.monotonic()-started,.5)
        self.assertTrue(watch.stopping)
        release.set();watch._thread.join(2)
        self.assertFalse(watch._thread.is_alive())
        self.assertFalse(watch.busy)
        self.assertIsNone(watch.status()['lastIndexedAt'])

    def test_canonical_inventory_ignores_private_noise_and_uses_no_image_decoder(self):
        watch=self.watch();watch.inventory_reader=image_manager._discovery_inventory
        (self.root/'inbox').mkdir()
        (self.root/'Picture.png').write_bytes(b'incomplete bytes are only statted here')
        with patch.object(image_manager,'_metadata',side_effect=AssertionError('Watcher must not decode')):
            with patch.object(image_manager,'_sha',side_effect=AssertionError('Watcher must not hash photos')):
                watch.tick(0);watch.tick(2)
                private=self.root/'.image-manager/history';private.mkdir(parents=True)
                (private/'old.png').write_bytes(b'private history')
                (self.root/'.image-import-own.png').write_bytes(b'private staging')
                watch.tick(4)
                self.assertEqual(len(self.calls),1)
                (self.root/'inbox/New.png').write_bytes(b'new candidate')
                watch.tick(6);watch.tick(8)
        self.assertEqual(len(self.calls),2)
        self.assertEqual({row['path'] for row in self.calls[-1]['inventory']},{'Picture.png','inbox/New.png'})
        for budget in ({'max_files':0},{'max_entries':0},{'max_directories':0},{'budget_seconds':-1}):
            with self.subTest(budget=budget):
                with self.assertRaises(image_manager.ImageManagerError) as raised:
                    image_manager._discovery_inventory(self.root,**budget)
                self.assertEqual(raised.exception.code,'inventory_limit')


if __name__=='__main__':
    unittest.main(verbosity=2)
