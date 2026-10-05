"""Trusted local operator configuration; never registers, starts or sends.

The contract file is an operator-reviewed record of an actual Chrome/Edge CUA
observation. Schema validation does not authenticate a JSON file's provenance,
observe Chrome/Edge, or verify Chat round trips. Do not relabel imported diagnostics
or synthetic fixtures as CUA evidence. The CLI has no alternate store option.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_chat_relay import (
    APPROVAL_KEY, ATTEMPT_PREFIX, BROWSER_SURFACES, EXTENSION_ID, HOST_NAME, MAX_FRAME,
    approval, encode, fixed_approval, timestamp,
)

APPROVAL_FILENAME = "console-chat-relay-approved.json"
BACKUP_DIRECTORY = "relay-configuration-backups"
MAX_CONTRACT_AGE_SECONDS = 30 * 60


class ConfigurationError(ValueError):
    """A fixed public error code; never interpolate private input or exceptions."""


def _require(condition, code):
    if not condition:
        raise ConfigurationError(code)


def _no_link(path):
    path = Path(path)
    _require(not path.is_symlink() and not (
        hasattr(path, "is_junction") and path.is_junction()
    ), "linked_configuration_path_rejected")


def fixed_directory(*, environ=None, directory=None):
    """Core injection supports disposable tests; CLI always uses LOCALAPPDATA."""
    environment = os.environ if environ is None else environ
    base = environment.get("LOCALAPPDATA", "")
    _require(isinstance(base, str) and base.strip(), "local_app_data_unavailable")
    base = Path(base)
    _require(base.is_absolute(), "local_app_data_must_be_absolute")
    parent = base / "CodexControlConsole"
    expected = parent / "workflow-private"
    _no_link(parent)
    _no_link(expected)
    expected = expected.resolve()
    if directory is not None:
        _no_link(Path(directory))
        _require(Path(directory).resolve() == expected, "fixed_store_identity_required")
    return expected


def _json(data):
    def distinct(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate_json_field_rejected")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=distinct)
    except ConfigurationError:
        raise
    except (ValueError, UnicodeError, TypeError):
        raise ConfigurationError("configuration_json_invalid") from None


def _file_bytes(path):
    _no_link(path)
    if not path.exists():
        return None
    _require(path.is_file() and path.stat().st_size <= MAX_FRAME,
             "configuration_file_invalid_or_too_large")
    return path.read_bytes()


def _connect(path, *, write=False):
    _no_link(path)
    _require(path.is_file(), "existing_workflow_store_required")
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                         uri=True, timeout=2, isolation_level=None)
    if not write:
        db.execute("PRAGMA query_only=ON")
    return db


def _setting(db):
    row = db.execute("SELECT value FROM settings WHERE key=?", (APPROVAL_KEY,)).fetchone()
    return row[0] if row else None


def _pair(db, directory, environment):
    raw = _setting(db)
    _require(raw is None or (isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_FRAME),
             "stored_approval_invalid")
    stored_value = _json(raw) if raw is not None else None
    file_bytes = _file_bytes(directory / APPROVAL_FILENAME)
    file_value = _json(file_bytes) if file_bytes is not None else None
    try:
        config = approval(stored_value, directory)
        file_config = approval(file_value, directory)
    except (ValueError, KeyError, TypeError, OSError):
        raise ConfigurationError("existing_approval_invalid_requires_review") from None
    # A deliberately disabled setting without a file is a normal inactive store.
    # Any present file must have an exactly matching semantic setting.
    _require(file_bytes is None or (raw is not None and file_value == stored_value),
             "existing_approval_pair_mismatch")
    _require(config == file_config, "existing_approval_pair_mismatch")
    try:
        _require(fixed_approval(environ=environment, directory=directory) == config,
                 "existing_approval_pair_mismatch")
    except ConfigurationError:
        raise
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        raise ConfigurationError("existing_approval_pair_mismatch") from None
    return config, raw, file_bytes


def _hash(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _public(directory, config=None, *, state="unconfigured", changed=False,
            code=None, backup=None, setting_present=False, file_present=False):
    usable = bool(config and config["domContract"]["verified"] is True
                  and config["domContract"]["surface"] in BROWSER_SURFACES)
    result = {
        "format": "codex-console-chat-relay-configuration", "version": 1,
        "state": state, "dataDir": str(directory), "hostName": HOST_NAME,
        "extensionId": EXTENSION_ID, "configured": config is not None,
        "runtimeContractEligible": usable, "changed": changed,
        "approvalSettingPresent": setting_present, "approvalFilePresent": file_present,
        "operations": {"configurationWritten": changed, "hostRegistered": False,
                       "relayStarted": False, "browserObserved": False,
                       "chatSent": False, "roundTripChecked": False},
    }
    if config:
        result.update(contractSha256=_hash(config["domContract"]),
                      contractDeclaredSource=config["domContract"]["source"],
                      contractDeclaredSurface=config["domContract"]["surface"],
                      contractDeclaredVerified=config["domContract"]["verified"],
                      approvalConfirmedAt=config["approvalConfirmedAt"])
    if code:
        result["code"] = code
    if backup:
        result["backupDir"] = str(backup)
    return result


def inspect_configuration(*, environ=None, directory=None):
    """Read-only, sanitized status. It does not connect to a broker or browser."""
    environment = os.environ if environ is None else environ
    directory = fixed_directory(environ=environment, directory=directory)
    try:
        with closing(_connect(directory / "workflow.sqlite3")) as db:
            config, raw, file_bytes = _pair(db, directory, environment)
        return _public(directory, config, state="configured" if config else "unconfigured",
                       setting_present=raw is not None, file_present=file_bytes is not None)
    except ConfigurationError as failure:
        return _public(directory, state="requires_review", code=str(failure))
    except (OSError, sqlite3.Error):
        return _public(directory, state="requires_review", code="configuration_status_unavailable")


def load_contract(path):
    """Read the operator's bounded JSON record; never claim provenance validation."""
    data = _file_bytes(Path(path))
    _require(data is not None, "reviewed_contract_file_required")
    value = _json(data)
    _require(isinstance(value, dict), "reviewed_contract_object_required")
    return value


def _reviewed_contract(contract, directory, confirmed_at, current_time):
    try:
        confirmed = timestamp(confirmed_at)
        current = current_time or datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.tzinfo is not None,
                 "current_time_invalid")
        # The human's authorization persists. Record its original timestamp;
        # never expire consent or manufacture a newer confirmation time.
        _require((current - confirmed).total_seconds() >= 0,
                 "user_approval_time_invalid_or_future")
        _require(isinstance(contract, dict) and type(contract.get("version")) is int,
                 "reviewed_browser_cua_contract_required")
        copied = _json(encode(contract))
        _require(copied.get("verified") is True and copied.get("surface") in BROWSER_SURFACES
                 and copied.get("source") == "cua", "reviewed_browser_cua_contract_required")
        captured = timestamp(copied.get("capturedAt"))
        _require((captured - current).total_seconds() <= 0,
                 "contract_capture_time_invalid")
        # Validate the exact runtime schema with harmless placeholders; this is
        # structural validation, not a browser observation or provenance claim.
        probe = {"version": 1, "enabled": True, "hostName": HOST_NAME,
                 "extensionId": EXTENSION_ID,
                 "pipeName": "\\\\.\\pipe\\codex-console-chat-relay-" + "0" * 32,
                 "authKeyHex": "0" * 64, "dataDir": str(directory),
                 "domContract": copied, "approvalConfirmedAt": confirmed_at,
                 "approvalVersion": 1}
        approval(probe, directory)
        return copied
    except ConfigurationError:
        raise
    except (ValueError, KeyError, TypeError, OSError, OverflowError):
        raise ConfigurationError("reviewed_browser_cua_contract_invalid") from None


def _idle_store(db):
    _require(not db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='settings' LIMIT 1").fetchone(),
             "settings_triggers_require_review")
    _require(not db.execute("SELECT 1 FROM idea_dispatches WHERE status IN ('claimed','waiting','needs_review') LIMIT 1").fetchone(),
             "dispatch_inflight_or_review_required")
    _require(not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone(),
             "work_inflight")
    for row in db.execute("SELECT value FROM settings WHERE key LIKE ?", (ATTEMPT_PREFIX + "%",)):
        entry = _json(row[0])
        _require(isinstance(entry, dict) and entry.get("phase") in {"completed", "failed"},
                 "relay_attempt_inflight_or_review_required")


def _atomic_replace(path, data, *, expected):
    """Replace only the value inspected by this operation, on the same volume."""
    _require(_file_bytes(path) == expected, "approval_file_changed_requires_review")
    temporary = path.with_name(path.name + ".configuration-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _require(_file_bytes(path) == expected, "approval_file_changed_requires_review")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _backup(directory, db_path, raw, file_bytes, contract):
    root = directory / BACKUP_DIRECTORY
    _no_link(root)
    root.mkdir(exist_ok=True)
    backup = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_") + uuid.uuid4().hex)
    backup.mkdir()
    database_backup = backup / "original-workflow.sqlite3"
    # Use a separate reader before the writer makes any changes. Copy pages in
    # small batches; never restore the entire DB over later unrelated work.
    with closing(_connect(db_path)) as source, closing(sqlite3.connect(database_backup)) as target:
        source.backup(target, pages=64)
    (backup / "original-approval-setting.json").write_bytes(encode({"present": raw is not None, "rawValue": raw}))
    if file_bytes is not None:
        (backup / "original-approved.json").write_bytes(file_bytes)
    metadata = {"format": "codex-console-chat-relay-configuration-backup", "version": 1,
                "phase": "prepared", "dataDir": str(directory), "hostName": HOST_NAME,
                "extensionId": EXTENSION_ID, "settingPresent": raw is not None,
                "approvalFilePresent": file_bytes is not None, "contractSha256": _hash(contract),
                "restoreScope": "Only the approval setting and approved JSON, after matching this operation's values."}
    (backup / "operation.json").write_bytes(encode(metadata))
    return backup


def _backup_phase(backup, phase):
    path = backup / "operation.json"
    previous = _file_bytes(path)
    value = _json(previous)
    value["phase"] = phase
    _atomic_replace(path, encode(value), expected=previous)


def _commit(db):
    """One fault-injection seam for isolated transaction failure checks."""
    db.commit()


def _restore_own_changes(directory, previous_raw, previous_file, new_raw, new_file):
    """Restore only our values, leaving subsequent external changes untouched."""
    with closing(_connect(directory / "workflow.sqlite3", write=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            current = _setting(db)
            _require(current in (previous_raw, new_raw), "recovery_setting_changed_requires_review")
            path = directory / APPROVAL_FILENAME
            contents = _file_bytes(path)
            _require(contents in (previous_file, new_file), "recovery_file_changed_requires_review")
            if contents == new_file:
                if previous_file is None:
                    _require(_file_bytes(path) == new_file, "recovery_file_changed_requires_review")
                    path.unlink()
                else:
                    _atomic_replace(path, previous_file, expected=new_file)
            if current == new_raw:
                if previous_raw is None:
                    db.execute("DELETE FROM settings WHERE key=? AND value=?", (APPROVAL_KEY, new_raw))
                else:
                    db.execute("UPDATE settings SET value=? WHERE key=? AND value=?", (previous_raw, APPROVAL_KEY, new_raw))
            db.commit()
        except BaseException:
            db.rollback()
            raise


def configure_configuration(contract, *, user_authorized, approval_confirmed_at,
                            environ=None, directory=None, current_time=None):
    """Trusted local operator entry; no registration/browser/start/send operations.

    Tests may inject LOCALAPPDATA and its matching private directory. The CLI
    cannot select another store. Consent and the schema are necessary inputs;
    neither authenticates imported JSON as a live CUA observation.
    """
    _require(user_authorized is True, "explicit_user_authorization_required")
    environment = os.environ if environ is None else environ
    directory = fixed_directory(environ=environment, directory=directory)
    contract = _reviewed_contract(contract, directory, approval_confirmed_at, current_time)
    db_path = directory / "workflow.sqlite3"
    db = None
    backup = None
    new_raw = new_file = previous_raw = previous_file = None
    try:
        db = _connect(db_path, write=True)
        db.execute("BEGIN IMMEDIATE")
        existing, previous_raw, previous_file = _pair(db, directory, environment)
        _idle_store(db)
        if existing:
            _require(existing["domContract"] == contract, "existing_configuration_change_requires_review")
            db.rollback()
            return _public(directory, existing, state="configured", setting_present=True, file_present=True)
        current = current_time or datetime.now(timezone.utc)
        _require((current - timestamp(contract["capturedAt"])).total_seconds() <= MAX_CONTRACT_AGE_SECONDS,
                 "recent_browser_cua_observation_required")
        candidate = {"version": 1, "enabled": True, "hostName": HOST_NAME,
                     "extensionId": EXTENSION_ID,
                     "pipeName": "\\\\.\\pipe\\codex-console-chat-relay-" + uuid.uuid4().hex,
                     "authKeyHex": secrets.token_hex(32), "dataDir": str(directory),
                     "domContract": contract, "approvalConfirmedAt": approval_confirmed_at,
                     "approvalVersion": 1}
        approval(candidate, directory)
        backup = _backup(directory, db_path, previous_raw, previous_file, contract)
        new_raw = encode(candidate).decode("utf-8")
        new_file = (new_raw + "\n").encode("utf-8")
        _require(_file_bytes(directory / APPROVAL_FILENAME) == previous_file,
                 "approval_file_changed_requires_review")
        db.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (APPROVAL_KEY, new_raw))
        # Until commit, readers see either no file or a file/store mismatch and
        # the unchanged runtime refuses to start. This tool never calls start.
        _atomic_replace(directory / APPROVAL_FILENAME, new_file, expected=previous_file)
        _commit(db)
        _require(fixed_approval(environ=environment, directory=directory) == candidate,
                 "configured_pair_verification_failed")
        _backup_phase(backup, "configured")
        return _public(directory, candidate, state="configured", changed=True, backup=backup,
                       setting_present=True, file_present=True)
    except BaseException as failure:
        if db is not None:
            try:
                db.rollback()
            except (OSError, sqlite3.Error):
                pass
            finally:
                db.close()
                db = None
        if backup is not None and new_raw is not None:
            try:
                _restore_own_changes(directory, previous_raw, previous_file, new_raw, new_file)
                _backup_phase(backup, "restored_after_failure")
            except BaseException:
                raise ConfigurationError("configuration_failed_recovery_requires_review") from None
            raise ConfigurationError("configuration_failed_prior_values_restored") from None
        if isinstance(failure, ConfigurationError):
            raise failure from None
        raise ConfigurationError("configuration_unavailable_no_approval_written") from None
    finally:
        if db is not None:
            db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Trusted LOCALAPPDATA operator configuration only; never registers, starts or sends.",
        epilog="A JSON source=cua field is not provenance proof. Submit only a complete actual Chrome/Edge CUA contract already reviewed by the trusted local operator, preserving its actual browser surface. Imported diagnostics and fixtures are not live acceptance evidence. Backups contain private data and remain in the existing private store.")
    parser.add_argument("mode", choices=("inspect", "configure"))
    parser.add_argument("--contract-file", help="Reviewed actual Chrome/Edge CUA contract JSON, preserving surface; not a diagnostic import")
    parser.add_argument("--user-authorized", action="store_true", help="Operator confirms the human explicitly authorized this fixed extension/host/page scope")
    parser.add_argument("--approval-confirmed-at", help="Original explicit human approval time, ISO 8601 with timezone; consent does not expire")
    parser.add_argument("--json", action="store_true", help="Emit sanitized status; no authentication key or pipe address")
    args = parser.parse_args(argv)
    if args.mode == "configure":
        if not args.contract_file or not args.user_authorized or not args.approval_confirmed_at:
            parser.error("configure requires --contract-file, --user-authorized and --approval-confirmed-at")
    elif args.contract_file or args.user_authorized or args.approval_confirmed_at:
        parser.error("inspect does not accept configuration inputs")
    try:
        result = (inspect_configuration() if args.mode == "inspect" else
                  configure_configuration(load_contract(args.contract_file),
                                          user_authorized=args.user_authorized,
                                          approval_confirmed_at=args.approval_confirmed_at))
    except ConfigurationError as failure:
        result = {"state": "refused", "code": str(failure), "configured": False,
                  "operations": {"hostRegistered": False, "relayStarted": False,
                                 "browserObserved": False, "chatSent": False}}
    except (OSError, sqlite3.Error):
        result = {"state": "refused", "code": "configuration_input_unavailable", "configured": False}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Configuration: " + result["state"] + ("; " + result["code"] if result.get("code") else ""))
        print("No host registration, browser observation, broker start or Chat send was performed.")
        if result.get("backupDir"):
            print("Private backup: " + result["backupDir"])
    return 2 if result["state"] in {"refused", "requires_review"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
