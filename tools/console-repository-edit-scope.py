"""Explicit current-turn ownership protocol for cooperating repository editors."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_repository_activity import ScopeError, ScopeStore, scan_rollout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("declare", "revoke", "inspect", "attest-terminal"))
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--mode", choices=("read-only", "read_only", "edit"))
    parser.add_argument("--repo", action="append", default=[])
    parser.add_argument("--receipt", help="Pinned native terminal receipt, including pre-capture rolloutFingerprint")
    parser.add_argument("--turn-id")
    parser.add_argument("--status", choices=("interrupted", "completed"))
    parser.add_argument("--scope-dir", type=Path)
    parser.add_argument("--state-path", action="append", type=Path)
    args = parser.parse_args(argv)
    store = ScopeStore(args.scope_dir, state_paths=args.state_path)
    try:
        if not args.thread_id:
            raise ScopeError("thread_id_required")
        if args.command in {"declare", "revoke"} and args.thread_id != os.environ.get("CODEX_THREAD_ID"):
            raise ScopeError("only_owner_thread_may_declare_or_revoke")
        if args.command == "declare":
            result = store.declare(args.thread_id, "read_only" if args.mode in {"read-only", "read_only"} else args.mode, args.repo)
        elif args.command == "revoke":
            store.revoke(args.thread_id)
            result = {"threadId": args.thread_id, "revoked": True}
        elif args.command == "inspect":
            record = store.thread_record(args.thread_id)
            scan = scan_rollout(record["rolloutPath"])
            result = {**record, "activity": scan, "declaration": store.resolve(args.thread_id, record["rolloutPath"], scan=scan)}
        else:
            if not args.receipt or not args.turn_id or not args.status:
                raise ScopeError("terminal_receipt_turn_and_status_required")
            result = store.attest_terminal(args.thread_id, verified_turn_id=args.turn_id,
                                          verified_status=args.status, evidence_path=args.receipt)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
