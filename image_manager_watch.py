"""Process-owned, local-only image discovery. Importing this module starts no work.

The core owns the canonical bounded stat inventory and the safe catalogue commit.
This scheduler only waits for stable observations and caches progress in memory.
It never applies an image plan or calls a synchronization provider.
"""
from datetime import datetime, timezone
import copy
import os
import re
import threading
import time

import image_manager


def _now():
    return datetime.now(timezone.utc).isoformat()


class ImageFolderWatch:
    def __init__(self, service, refresh_callback, *, interval=2.0, settle=2.0,
                 retry_delay=5.0, max_backoff=60.0, join_timeout=1.0,
                 clock=time.monotonic, wall_clock=_now, inventory_reader=None):
        if not callable(refresh_callback):
            raise TypeError('A local refresh callback is required')
        self.service, self.refresh_callback = service, refresh_callback
        self.interval, self.settle = max(0.05,float(interval)), max(0.0,float(settle))
        self.retry_delay = max(self.interval,float(retry_delay))
        self.max_backoff = max(self.retry_delay,float(max_backoff))
        self.join_timeout = max(0.0,min(2.0,float(join_timeout)))
        self.clock, self.wall_clock = clock, wall_clock
        self.inventory_reader = inventory_reader
        self._lock, self._tick_lock = threading.RLock(), threading.Lock()
        self._stop, self._wake = threading.Event(), threading.Event()
        self._thread, self._closed = None, False
        self._processing = False
        self._binding, self._observed, self._indexed = None, None, None
        self._stable_since, self._retry_at, self._failures = None, 0.0, 0
        self._status_version = 0
        self._status = {'root':'','status':'checking','pending':True,'reason':'initial_probe',
                        'lastCheckedAt':None,'lastIndexedAt':None,'counts':{'images':0},
                        'changeToken':None,'localRevision':None,'statusRevision':'0'}

    def _publish(self, **changes):
        with self._lock:
            important = any(key not in {'lastCheckedAt','lastIndexedAt'} and self._status.get(key)!=value
                            for key,value in changes.items())
            self._status.update(changes)
            if important:
                self._status_version += 1
                self._status['statusRevision'] = str(self._status_version)

    def status(self, expectedRoot=None):
        """Pure cached projection; this never checks a path, lock or metadata file."""
        with self._lock:
            value = copy.deepcopy(self._status)
        if expectedRoot is not None and os.path.normcase(str(expectedRoot))!=os.path.normcase(value['root']):
            value.update(root=str(expectedRoot),status='checking',pending=True,reason='root_pending',
                         lastCheckedAt=None,lastIndexedAt=None,counts={'images':0},
                         changeToken=None,localRevision=None)
        return value

    def start(self):
        with self._lock:
            if self._closed or self._thread and self._thread.is_alive():
                return self
            self._thread = threading.Thread(target=self._run,name='console-image-local-watch',daemon=True)
            self._thread.start()
        return self

    @property
    def stopping(self):
        return self._stop.is_set()

    @property
    def busy(self):
        with self._lock:
            return self._processing

    def poke(self):
        """Wake the existing process-owned worker; never refresh from this caller."""
        if not self._closed:
            self._wake.set()

    def close(self):
        with self._lock:
            self._closed = True
            self._stop.set()
            self._wake.set()
            worker = self._thread
        if worker and worker is not threading.current_thread():
            worker.join(self.join_timeout)
        self._publish(status='deferred' if self.status()['pending'] else 'ready',reason='stopped')

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            self._wake.wait(self.interval)
            self._wake.clear()

    def _error(self, reason, now):
        self._failures = min(self._failures+1,8)
        self._retry_at = now + min(self.max_backoff,self.retry_delay*(2**(self._failures-1)))
        self._publish(status='error',pending=True,reason=reason)

    def tick(self, now=None):
        """One stat observation, useful for deterministic tests. No overlapping ticks."""
        if self._closed or not self._tick_lock.acquire(blocking=False):
            return self.status()
        try:
            self._tick(self.clock() if now is None else float(now))
        finally:
            self._tick_lock.release()
        return self.status()

    def _tick(self, now):
        try:
            config = self.service._config()
            configured = config.get('root','')
            identity = config.get('rootIdentity')
            binding = (os.path.normcase(configured),tuple(identity or ()))
            if binding != self._binding:
                self._binding = binding
                self._observed = self._indexed = self._stable_since = None
                self._retry_at, self._failures = 0.0, 0
                self._publish(root=configured,status='checking',pending=bool(configured),reason='initial_probe',
                              changeToken=None,localRevision=None,lastIndexedAt=None,counts={'images':0})
            if not configured:
                self._publish(status='ready',pending=False,reason='not_configured')
                return
            root = image_manager._safe_directory(configured)
            if image_manager._identity(root) != identity:
                raise image_manager.ImageManagerError('Configured root identity changed',status=409)
            reader = self.inventory_reader or image_manager._discovery_inventory
            inventory = reader(root)
            if (not isinstance(inventory,dict) or not isinstance(inventory.get('inventory'),list)
                    or not isinstance(inventory.get('inventoryToken'),str)
                    or not re.fullmatch('[0-9a-f]{64}',inventory['inventoryToken'])):
                raise ValueError('Invalid bounded inventory response')
            token = inventory['inventoryToken']
            self._publish(lastCheckedAt=self.wall_clock(),counts={'images':len(inventory['inventory'])},changeToken=token)
            if token == self._indexed:
                self._publish(status='ready',pending=False,reason='up_to_date')
                return
            if token != self._observed:
                self._observed,self._stable_since = token,now
                self._retry_at,self._failures = 0.0,0
                self._publish(status='settling',pending=True,reason='files_settling')
                return
            if now-self._stable_since < self.settle:
                self._publish(status='settling',pending=True,reason='files_settling')
                return
            if now < self._retry_at or self._stop.is_set():
                return
            payload = {'expectedRoot':str(root),'inventoryToken':token,'inventory':copy.deepcopy(inventory['inventory'])}
            with self._lock:
                self._processing = True
            try:
                result = self.refresh_callback(payload)
            finally:
                with self._lock:
                    self._processing = False
            if self._stop.is_set():
                return
            if not isinstance(result,dict) or result.get('status') not in {'updated','noop','deferred'}:
                raise ValueError('Invalid local refresh response')
            if result.get('root') is not None and os.path.normcase(result['root'])!=os.path.normcase(str(root)):
                raise ValueError('Local refresh returned another root')
            if result['status']=='deferred':
                self._retry_at = now+self.retry_delay
                reason = result.get('reason','local_busy')
                if not isinstance(reason,str) or not re.fullmatch('[a-z0-9_]{1,80}',reason):
                    reason = 'local_busy'
                self._publish(status='deferred',pending=True,reason=reason)
                return
            self._indexed = token
            self._failures,self._retry_at = 0,0.0
            self._publish(status='changed' if result['status']=='updated' else 'ready',pending=False,
                          reason='local_updated' if result['status']=='updated' else 'up_to_date',
                          lastIndexedAt=self.wall_clock(),localRevision=result.get('localRevision'))
        except Exception as error:
            reason = getattr(error,'code','inventory_error')
            if not isinstance(reason,str) or not re.fullmatch('[a-z0-9_]{1,80}',reason):
                reason = 'inventory_error'
            self._error(reason,now)
