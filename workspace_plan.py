"""Private per-device task-plan seed. User content is never bundled for release."""
import json
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading

MAX_PLAN_BYTES = 128 * 1024
MAX_PLAN_STATE_BYTES = MAX_PLAN_BYTES * 2 + 4096
_STATE_LOCK = threading.RLock()


class PlanStateConflict(ValueError):
    """A newer saved plan must not be replaced by an old browser."""


def _text(value, label, limit, optional=False):
    if optional and value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError(f'{label} must be text')
    value = value.strip()
    if (not optional and not value) or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError(f'{label} is empty, too long, or contains control characters')
    return value


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,119}', value):
        raise ValueError('Plan identifiers must be 1-120 simple characters')
    return value


def _normalize_plan(value, minimum_groups, maximum_groups):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Unsupported workspace plan version')
    revision = _identifier(value.get('revision'))
    groups = value.get('groups')
    if not isinstance(groups, list) or not minimum_groups <= len(groups) <= maximum_groups:
        raise ValueError('Workspace plan task-group count is invalid')
    result, group_ids, item_ids = [], set(), set()
    total = 0
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('Invalid workspace group')
        identifier = _identifier(group.get('id'))
        if identifier in group_ids:
            raise ValueError('Duplicate workspace group id')
        group_ids.add(identifier)
        items = group.get('items')
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError('Workspace group must have no more than 100 items')
        total += len(items)
        if total > 300:
            raise ValueError('Workspace plan has too many items')
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid workspace item')
            item_id = _identifier(item.get('id'))
            if item_id in item_ids or type(item.get('done')) is not bool:
                raise ValueError('Duplicate item id or invalid done flag')
            item_ids.add(item_id)
            normalized.append({'id': item_id, 'text': _text(item.get('text'), 'Task', 500), 'done': item['done']})
        result.append({'id': identifier, 'title': _text(group.get('title'), 'Group title', 120),
                       'summary': _text(group.get('summary'), 'Group summary', 240, optional=True),
                       'items': normalized})
    return {'version': 1, 'revision': revision, 'groups': result}


def normalize_plan(value):
    return _normalize_plan(value, 4, 4)


def normalize_actual_plan(value):
    # Existing public installations may have six groups. Preserve those tasks
    # while keeping a private seed subject to the original four-group contract.
    return _normalize_plan(value, 1, 12)


def read_plan(data_dir):
    path = Path(data_dir) / 'workspace-plan.json'
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise ValueError('Workspace plan exceeds 128 KiB')
        return {'plan': normalize_plan(json.loads(raw.decode('utf-8-sig'))), 'error': ''}
    except FileNotFoundError:
        return {'plan': None, 'error': ''}
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        return {'plan': None, 'error': f'Could not load the local task plan; saved tasks were kept. {error}'}


def plan_script(payload):
    # Escape '<' as well as non-ASCII separators to remain inert in all JS contexts.
    encoded = json.dumps(payload.get('plan'), ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')
    error = json.dumps(payload.get('error', ''), ensure_ascii=True).replace('<', '\\u003c')
    return f'window.CODEX_WORKSPACE_PLAN={encoded};\nwindow.CODEX_WORKSPACE_PLAN_ERROR={error};\n'.encode('utf-8')


def _plan_hash(plan):
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError('Workspace plan exceeds 128 KiB')
    return hashlib.sha256(raw).hexdigest()


def _state_path(data_dir):
    return Path(data_dir) / 'workspace-plan-state.json'


def _read_state_file(data_dir):
    path = _state_path(data_dir)
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_PLAN_STATE_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_PLAN_STATE_BYTES:
        raise ValueError('Saved workspace plan exceeds its size limit')
    value = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(value, dict) or type(value.get('stateVersion')) is not int or value['stateVersion'] != 1:
        raise ValueError('Unsupported saved workspace plan version')
    plan = normalize_actual_plan(value.get('plan'))
    seed = normalize_plan(value['seed']) if value.get('seed') is not None else None
    updated = value.get('updatedAt')
    if not isinstance(updated, str) or len(updated) > 60:
        raise ValueError('Invalid saved workspace plan time')
    try:
        timestamp = datetime.fromisoformat(updated.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError('Invalid saved workspace plan time') from None
    seed_revision = seed['revision'] if seed else None
    if value.get('hash') != _plan_hash(plan) or value.get('seedRevision') != seed_revision or seed and plan['revision'] != seed_revision:
        raise ValueError('Saved workspace plan hash or seed revision is invalid')
    return {'stateVersion': 1, 'plan': plan, 'seed': seed, 'seedRevision': seed_revision,
            'hash': value['hash'], 'updatedAt': updated}


def _write_state(data_dir, plan, seed):
    state = {'stateVersion': 1, 'plan': plan, 'seed': seed, 'seedRevision': seed['revision'] if seed else None,
             'hash': _plan_hash(plan), 'updatedAt': datetime.now(timezone.utc).isoformat()}
    raw = json.dumps(state, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    if len(raw) > MAX_PLAN_STATE_BYTES:
        raise ValueError('Saved workspace plan exceeds its size limit')
    target = _state_path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.workspace-plan-state.', suffix='.tmp', dir=str(target.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            descriptor = -1
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return state


def _merge_seed(plan, before, after):
    """Carry saved edits across a seed update without resurrecting deletions."""
    before_groups = {group['id']: group for group in before['groups']}
    after_groups = {group['id']: group for group in after['groups']}
    if set(before_groups) != set(after_groups) or {group['id'] for group in plan['groups']} != set(before_groups):
        raise ValueError('The updated plan categories require an explicit migration')
    old_owners = {item['id']: group['id'] for group in before['groups'] for item in group['items']}
    saved_owners = {item['id']: group['id'] for group in plan['groups'] for item in group['items']}
    if any(identifier in old_owners and old_owners[identifier] != owner for identifier, owner in saved_owners.items()):
        raise ValueError('Saved plan item ownership requires an explicit migration')
    for group in after['groups']:
        for item in group['items']:
            old_owner, saved_owner = old_owners.get(item['id']), saved_owners.get(item['id'])
            if old_owner and old_owner != group['id'] or not old_owner and saved_owner:
                raise ValueError('The updated plan item identifiers conflict with saved tasks')
    groups = []
    for group in plan['groups']:
        old, new = before_groups[group['id']], after_groups[group['id']]
        old_items, new_items = ({item['id']: item for item in seed['items']} for seed in (old, new))
        items = []
        for item in group['items']:
            old_item, new_item = old_items.get(item['id']), new_items.get(item['id'])
            if old_item and not new_item:
                continue
            item = dict(item)
            if old_item and new_item:
                if old_item['text'] != new_item['text']:
                    item['text'] = new_item['text']
                if old_item['done'] != new_item['done'] and item['done'] == old_item['done']:
                    item['done'] = new_item['done']
            items.append(item)
        items.extend(dict(item) for item in new['items'] if item['id'] not in old_items)
        groups.append({'id': group['id'], 'title': new['title'] if old['title'] != new['title'] else group['title'],
                       'summary': new['summary'] if old['summary'] != new['summary'] else group['summary'], 'items': items})
    return normalize_plan({'version': 1, 'revision': after['revision'], 'groups': groups})


def _current_state(data_dir):
    state = _read_state_file(data_dir)
    if state is None:
        return None
    seed_result = read_plan(data_dir)
    if seed_result['error']:
        raise ValueError('The local seed could not be read; saved tasks were kept')
    seed = seed_result['plan']
    if seed is not None and seed != state['seed']:
        if state['seed'] is None:
            raise ValueError('Adding a private seed requires an explicit migration; saved public tasks were kept')
        # Save the entire merged snapshot before advertising a new content hash.
        state = _write_state(data_dir, _merge_seed(state['plan'], state['seed'], seed), seed)
    return state


def read_plan_state(data_dir):
    """Read the effective saved tasks, never hiding a broken state with a seed."""
    with _STATE_LOCK:
        try:
            state = _current_state(data_dir)
            if state is None:
                return {'persisted': False, 'plan': None, 'hash': None, 'updatedAt': None, 'actualDone': False, 'error': ''}
            return {**state, 'persisted': True, 'actualDone': True, 'error': ''}
        except (OSError, ValueError, UnicodeError, RuntimeError) as error:
            return {'persisted': False, 'plan': None, 'hash': None, 'updatedAt': None,
                    'actualDone': False, 'error': f'Could not read saved tasks; previous data was kept. {error}'}


def read_actual_plan(data_dir):
    result = read_plan_state(data_dir)
    if result['persisted'] or result['error']:
        return result
    return {**result, **read_plan(data_dir)}


def save_plan_state(data_dir, value, expected_hash):
    """Atomically store one browser snapshot with optimistic concurrency."""
    if expected_hash is not None and (not isinstance(expected_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', expected_hash)):
        raise ValueError('Invalid saved workspace plan hash')
    plan = normalize_actual_plan(value)
    candidate_hash = _plan_hash(plan)
    with _STATE_LOCK:
        current = _current_state(data_dir)
        current_hash = current['hash'] if current else None
        if current_hash != expected_hash:
            # A lost successful HTTP response may be retried without rewriting
            # a newer plan or advancing its recorded save time.
            if current and candidate_hash == current_hash:
                return {**current, 'persisted': True, 'actualDone': True, 'error': ''}
            raise PlanStateConflict('A newer task plan is already saved; local edits were kept')
        seed_result = read_plan(data_dir)
        if seed_result['error']:
            raise ValueError('The local seed could not be read; saved tasks were kept')
        seed = seed_result['plan'] or (current['seed'] if current else None)
        if seed is not None and plan['revision'] != seed['revision']:
            raise PlanStateConflict('The task-plan seed changed; reload before saving')
        if seed is not None and {group['id'] for group in plan['groups']} != {group['id'] for group in seed['groups']}:
            raise ValueError('Saved tasks must retain the four local plan categories')
        if current and candidate_hash == current_hash:
            state = current
        else:
            state = _write_state(data_dir, plan, seed)
        return {**state, 'persisted': True, 'actualDone': True, 'error': ''}
