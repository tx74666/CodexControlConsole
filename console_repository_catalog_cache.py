"""Identity-bound display snapshots with bounded, deduplicated catalog readers.

These snapshots never authorize version writes, commits or pushes. Those keep
the publisher's fresh repository/authority checks. No model calls or idle scans.
"""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from console_repository_publish import RepositoryPublishError, catalog_source_identity


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class RepositoryCatalogCache:
    def __init__(self, publisher, *, identity_scope='', workers=2, deadline_seconds=30):
        self.publisher = publisher
        self.cache_identity = _digest({'schema': 1, 'dataset': str(publisher.state_dir.resolve()),
                                       'installationScope': str(identity_scope)})
        self.path = publisher.state_dir / 'catalog-display-cache.json'
        self.deadline_seconds = deadline_seconds
        self.worker_count = max(1, min(2, int(workers)))
        self._condition = threading.Condition(threading.RLock())
        self._records, self._states, self._signatures = {}, {}, {}
        self._queue, self._queued, self._running = deque(), set(), set()
        self._threads, self._closed = [], False
        self._load()

    def _load(self):
        try:
            if not self.path.is_file() or self.path.stat().st_size > 4 * 1024 * 1024:
                return
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if value.get('schema') != 1 or value.get('cacheIdentity') != self.cache_identity:
                return
            records = value.get('records', {})
            if not isinstance(records, dict):
                return
            for identifier, record in records.items():
                if (isinstance(record, dict) and isinstance(record.get('item'), dict)
                        and isinstance(record.get('sourceIdentity'), str)
                        and len(record['sourceIdentity']) == 64
                        and isinstance(record.get('checkedAt'), str)
                        and record['item'].get('repoId') == identifier
                        and isinstance(record['item'].get('components'), list)
                        and all(isinstance(item, dict) for item in record['item']['components'])):
                    self._records[identifier] = _copy(record)
        except (OSError, ValueError, TypeError, KeyError):
            pass  # A broken display cache cannot block publishing or erase data.

    def _persist_locked(self):
        value = {'schema': 1, 'cacheIdentity': self.cache_identity, 'records': self._records}
        data = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode()
        if len(data) > 4 * 1024 * 1024:
            return
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            pass  # Existing snapshots remain available; no mutation depends on cache.
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _settings(self):
        settings = self.publisher._settings()
        repositories = settings.get('repositories', [])
        if not isinstance(repositories, list):
            raise RepositoryPublishError('仓库配置暂时无法读取。')
        return settings

    def _observe_locked(self, settings):
        repositories = settings['repositories']
        signatures = {row['id']: catalog_source_identity(row, settings.get('naming', {}))
                      for row in repositories}
        for identifier, signature in signatures.items():
            previous = self._signatures.get(identifier)
            record = self._records.get(identifier)
            if record and record.get('sourceIdentity') != signature:
                self._records.pop(identifier, None)
                record = None
            if previous != signature:
                self._states[identifier] = {'sourceIdentity': signature, 'state': 'idle',
                                            'startedAt': '', 'checkedAt': (record or {}).get('checkedAt', ''),
                                            'message': '', 'diagnostic': None}
        for identifier in set(self._records) - set(signatures):
            self._records.pop(identifier, None)
        for identifier in set(self._states) - set(signatures):
            self._states.pop(identifier, None)
        self._signatures = signatures
        return signatures

    def _snapshot_locked(self, identifiers):
        rows, states = [], {}
        for identifier in identifiers:
            state = _copy(self._states[identifier])
            states[identifier] = state
            record = self._records.get(identifier)
            if not record or record['sourceIdentity'] != self._signatures[identifier]:
                continue
            item = _copy(record['item'])
            item.update(sourceIdentity=record['sourceIdentity'], checkedAt=record['checkedAt'],
                        displayOnly=state['state'] != 'ready')
            if item['displayOnly']:
                for component in item.get('components', []):
                    component['canBump'] = False
            rows.append(item)
        refreshing = [identifier for identifier in identifiers
                      if states[identifier]['state'] in {'queued', 'reading'}]
        return {'cacheIdentity': self.cache_identity, 'repositories': rows, 'versionSnapshots': rows,
                'versionSources': [{'repoId': identifier, 'sourceIdentity': self._signatures[identifier]}
                                   for identifier in identifiers],
                'versionReadStates': states, 'refreshingIds': refreshing, 'complete': not refreshing}

    def status(self):
        # The existing base metadata read is fast and keeps live operation receipts.
        result = self.publisher.status()
        with self._condition:
            settings = result['settings']
            signatures = self._observe_locked(settings)
            result.update(self._snapshot_locked(list(signatures)))
        return result

    def snapshot(self, repo_id=None, *, refresh=False):
        if not self.publisher.allowed:
            raise RepositoryPublishError('当前入口不允许读取版本配置。')
        settings = self._settings()
        with self._condition:
            signatures = self._observe_locked(settings)
            if repo_id is not None and repo_id not in signatures:
                raise RepositoryPublishError('仓库编号不存在。')
            identifiers = [repo_id] if repo_id is not None else list(signatures)
            if refresh and not self._closed:
                enabled = {row['id'] for row in settings['repositories'] if row.get('enabled', True)}
                for identifier in identifiers:
                    if repo_id is None and identifier not in enabled:
                        continue
                    signature = signatures[identifier]
                    key = (identifier, signature)
                    if key in self._queued or key in self._running:
                        continue
                    state = self._states[identifier]
                    # Two simultaneous windows or rapid repeated refreshes deduplicate.
                    if state.get('completedMonotonic') and time.monotonic() - state['completedMonotonic'] < 2:
                        continue
                    self._queue.append(key)
                    self._queued.add(key)
                    state.update(state='queued', startedAt=_now(), message='', diagnostic=None)
                if self._queue:
                    self._threads = [thread for thread in self._threads if thread.is_alive()]
                    while len(self._threads) < self.worker_count:
                        thread = threading.Thread(target=self._read_loop, daemon=True,
                                                  name='repository-display-reader')
                        try:
                            thread.start()
                        except RuntimeError:
                            if not self._threads:
                                while self._queue:
                                    failed = self._queue.popleft()
                                    self._queued.discard(failed)
                                    failed_id, failed_signature = failed
                                    if self._signatures.get(failed_id) == failed_signature:
                                        self._states[failed_id].update(state='error',
                                            message='后台读取暂时无法启动，保留上次记录；可单独重试。')
                            break
                        self._threads.append(thread)
                    self._condition.notify_all()
            return self._snapshot_locked(identifiers)

    def seed_display(self, rows, *, checked_at=None):
        """Migrate an already-read legacy catalog as last-known display data only."""
        settings = self._settings()
        with self._condition:
            signatures = self._observe_locked(settings)
            for item in rows:
                identifier = item.get('repoId')
                if identifier in signatures and isinstance(item.get('components'), list):
                    self._records[identifier] = {'sourceIdentity': signatures[identifier],
                                                 'checkedAt': checked_at or _now(), 'item': _copy(item)}
                    self._states[identifier]['checkedAt'] = self._records[identifier]['checkedAt']
            self._persist_locked()

    def _read_loop(self):
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                identifier, signature = self._queue.popleft()
                key = (identifier, signature)
                self._queued.discard(key)
                if self._signatures.get(identifier) != signature:
                    continue
                self._running.add(key)
                self._states[identifier].update(state='reading', startedAt=_now())
            item, message = None, ''
            try:
                result = self.publisher.version_catalog(identifier, deadline_seconds=self.deadline_seconds)
                item = next((row for row in result['repositories'] if row['repoId'] == identifier), None)
                if item is None:
                    message = '仓库读取未返回结果，保留上次记录。'
                elif item.get('sourceIdentity') != signature:
                    item = None
                    message = '读取期间仓库配置已变化，保留上次记录；可重新核对。'
                elif item.get('readState') == 'error':
                    # Fallback titles, sync reasons and old upload warnings are
                    # informative catalog results, not failed version reads.
                    message = item.get('message') or '仓库读取失败，保留上次记录；可单独重试。'
            except (OSError, RuntimeError, ValueError, TypeError, KeyError, RepositoryPublishError):
                message = '仓库读取失败或超时，保留上次记录；可单独重试。'
            try:
                current = self._settings()
            except (OSError, ValueError, RepositoryPublishError):
                current = None
            with self._condition:
                self._running.discard(key)
                if self._closed:
                    return
                if current is not None:
                    self._observe_locked(current)
                if current is None or self._signatures.get(identifier) != signature:
                    continue  # A late old-target result cannot overwrite new settings.
                state = self._states[identifier]
                state.update(state='error' if message else 'ready', message=message,
                             diagnostic=_copy(item.get('diagnostic')) if message and item is not None else None,
                             completedMonotonic=time.monotonic())
                if item is not None and (not message or identifier not in self._records):
                    self._records[identifier] = {'sourceIdentity': signature, 'checkedAt': _now(), 'item': _copy(item)}
                if identifier in self._records:
                    state['checkedAt'] = self._records[identifier]['checkedAt']
                self._persist_locked()

    def close(self):
        with self._condition:
            self._closed = True
            self._queue.clear()
            self._queued.clear()
            self._condition.notify_all()
        for thread in self._threads:
            thread.join(timeout=.2)
