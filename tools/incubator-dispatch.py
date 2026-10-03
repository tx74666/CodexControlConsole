"""Private local outbox operations for an authorized Codex heartbeat.

Never invokes a model, message tool, GUI, shell, or external executable. Only the
explicit publish HTTP action can create pending dispatches; this CLI consumes
their stored user confirmation and writes actual tool receipts/results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError, WorkflowService

MAX_INPUT = 128 * 1024


def read_body(filename):
    if filename:
        path = Path(filename)
        if path.stat().st_size > MAX_INPUT:
            raise WorkflowError("队列操作输入过大。", 413)
        with path.open(encoding="utf-8-sig") as source:
            text = source.read(MAX_INPUT + 1)
    else:
        text = sys.stdin.read(MAX_INPUT + 1)
    if len(text.encode("utf-8")) > MAX_INPUT:
        raise WorkflowError("队列操作输入过大。", 413)
    body = json.loads(text)
    if not isinstance(body, dict):
        raise WorkflowError("队列操作须为 JSON 对象。")
    return body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, help="现有私有 workflow.sqlite3 所在绝对目录")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="只读全部发布记录；不会认领或发送")
    commands.add_parser("read-waiting", help="只读 claimed/waiting/needs_review，含私有 claimToken 与授权快照")
    claim = commands.add_parser("claim", help="原子认领一个 pending（高优先级先到先出）；不会发送")
    claim.add_argument("--request-id", required=True)
    claim.add_argument("--id", help="可选固定 dispatch ID；已认领不可重复认领")
    for name in ("attach-result", "fail", "targets"):
        command = commands.add_parser(name, help="JSON 输入经文件或 stdin；不会调用任何聊天工具")
        command.add_argument("--json-file")
        command.add_argument("--request-id", help="覆写/补入 requestId；targets 缺省按快照内容生成稳定 UUID")
    args = parser.parse_args(argv)
    directory = Path(args.data_dir)
    if not directory.is_absolute() or not (directory / "workflow.sqlite3").is_file():
        raise WorkflowError("请指定已经存在的私有 workflow 数据目录。", 404)
    # Do not recover live jobs or claimed dispatches when opening a CLI writer.
    service = WorkflowService(directory, recover_jobs=False)
    if args.command == "list":
        result = service.incubator_dispatches()
    elif args.command == "read-waiting":
        result = service.incubator_dispatches(waiting=True, private=True)
    elif args.command == "claim":
        body = {"requestId": args.request_id}
        if args.id is not None:
            body["id"] = args.id
        result = service.incubator_claim(body)
    else:
        body = read_body(args.json_file)
        if args.request_id:
            body["requestId"] = args.request_id
        if args.command == "targets" and "requestId" not in body:
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            body["requestId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "console-incubator-targets:" + digest))
        operation = {"attach-result": service.incubator_attach_result, "fail": service.incubator_fail,
                     "targets": service.incubator_set_targets}[args.command]
        result = operation(body)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(main())
    except (WorkflowError, OSError, sqlite3.Error, ValueError) as error:
        # Internal paths, credentials and upstream exception details stay private.
        message = str(error) if isinstance(error, WorkflowError) else "队列操作未完成，请检查本机输入文件或数据目录。"
        print(json.dumps({"error": message, "code": getattr(error, "code", "invalid_request"),
                          "status": getattr(error, "status", 400)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
