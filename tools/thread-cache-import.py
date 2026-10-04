"""Normalize a real read_thread response into the existing private cache.

No model, browser, shell, network or chat sending. Original App Tools text is
kept as a source view; missing images/logs and truncation remain explicit.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError, WorkflowService

def source_time(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            time = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if time.tzinfo:
                return time.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return None

def normalize(body):
    keys = {'requestId','threadId','generation','mode','cursor','fetchedAt','source'}
    if not isinstance(body, dict) or set(body)-keys:
        raise WorkflowError('实际会话读取输入无效。')
    source = body.get('source')
    if not isinstance(source, dict) or source.get('thread', {}).get('id') != body.get('threadId'):
        raise WorkflowError('来源会话与缓存目标不一致。')
    page = source.get('page')
    turns = source.get('turns')
    if not isinstance(page, dict) or not isinstance(turns, list) or page.get('order') not in {'newest_first','oldest_first'}:
        raise WorkflowError('来源没有提供可核对的消息分页。')
    if type(page.get('hasMore')) is not bool or (page['hasMore'] and not isinstance(page.get('nextCursor'), str)):
        raise WorkflowError('来源历史范围或游标不明确。')
    ordered = list(reversed(turns)) if page['order']=='newest_first' else turns
    messages, omitted, dates = {}, 0, []
    for turn in ordered:
        if not isinstance(turn, dict) or not isinstance(turn.get('id'), str):
            raise WorkflowError('来源回合标识无效。')
        for name in ('startedAt', 'completedAt'):
            time = source_time(turn.get(name))
            if time:
                dates.append(time)
        ordinal = 0
        for item in turn.get('items', []):
            if not isinstance(item, dict) or item.get('type') not in {'userMessage','agentMessage'}:
                omitted += 1
                continue
            role = 'user' if item['type']=='userMessage' else 'assistant'
            parts = item.get('content') if role=='user' else None
            images = 0
            if isinstance(parts, list):
                text_parts = []
                for part in parts:
                    if isinstance(part, dict) and isinstance(part.get('text'), str):
                        text_parts.append(part['text'])
                    else:
                        images += 1
                text = '\n'.join(text_parts)
            else:
                text = item.get('text', '')
            if not isinstance(text, str):
                raise WorkflowError('来源消息文字格式无效。')
            if images:
                text += f'\n[此消息另含 {images} 项图片或附件；此处仅取得文字。]'
            truncated = bool(item.get('truncated')) or len(text)>20000
            if len(text)>20000:
                text = text[:19920]+'\n[此条超过缓存上限，后续文字未获取。]'
            raw_id = item.get('id')
            identifier = raw_id if isinstance(raw_id, str) and raw_id else 'derived-'+hashlib.sha256(f"{turn['id']}:{role}:{ordinal}".encode()).hexdigest()
            ordinal += 1
            message = {'id':identifier,'role':role,'text':text,'turnId':turn['id'],'truncated':truncated}
            if isinstance(raw_id, str) and raw_id:
                message['sourceMessageId'] = raw_id
            if isinstance(item.get('phase'), str):
                message['phase'] = item['phase']
            if isinstance(turn.get('status'), (str, dict)):
                message['status'] = turn['status']
            if source_time(item.get('createdAt')):
                message['createdAt'] = source_time(item['createdAt'])
            messages[identifier] = message
    values = list(messages.values())
    dropped = max(0,len(values)-256)
    if dropped:
        values = values[-256:]
    coverage = {'description':f'App Tools 消息文字视图（可能含来源摘要）：本页 {len(turns)} 回合；工具日志、图片及附件未获取。'}
    if omitted:
        coverage['description'] += f' 另有 {omitted} 项工具或过程条目未保存。'
    if dropped:
        coverage['description'] += f' 本页较早 {dropped} 条超过缓存条数限制。'
    if dates:
        coverage.update(oldestAt=min(dates),newestAt=max(dates))
    return {k:body[k] for k in ('requestId','threadId','generation','mode','fetchedAt')} | {
        'cursor':body.get('cursor',''), 'olderCursor':page['nextCursor'] if page['hasMore'] else None,
        'partial':True, 'coverage':coverage, 'messages':values}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--json-file', required=True)
    args = parser.parse_args()
    directory, source = Path(args.data_dir), Path(args.json_file)
    if not directory.is_absolute() or not (directory/'workflow.sqlite3').is_file():
        raise WorkflowError('请指定现有私有会话库。',404)
    if source.stat().st_size>8*1024*1024:
        raise WorkflowError('来源会话读取超过导入上限。',413)
    body = json.loads(source.read_text(encoding='utf-8-sig'))
    result = WorkflowService(directory,recover_jobs=False).conversations_thread_snapshot(normalize(body))
    print(json.dumps({'threadId':body['threadId'],'coverage':result['coverage'],'ignored':result.get('ignored',False),'duplicate':result.get('duplicate',False)},ensure_ascii=False))

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8',errors='replace')
        sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    try:
        main()
    except (WorkflowError,OSError,ValueError) as error:
        print(json.dumps({'error':str(error) if isinstance(error,WorkflowError) else '会话读取导入失败，请检查来源与私有输入文件。'},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
