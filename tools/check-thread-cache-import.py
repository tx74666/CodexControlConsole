"""Check actual App Tools format normalization with isolated cache fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_service import WorkflowError, WorkflowService
path = Path(__file__).with_name('thread-cache-import.py')
spec = importlib.util.spec_from_file_location('thread_cache_import', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ID = '01a0fb88-0c96-7121-bd84-31b640b87f71'

def fixture():
    return {'requestId':str(uuid.uuid4()),'threadId':ID,'generation':1,'mode':'refresh','cursor':'',
            'fetchedAt':'2026-10-04T00:00:00Z','source':{'thread':{'id':ID,'kind':'codex'},
            'page':{'order':'newest_first','hasMore':True,'nextCursor':'opaque-older'},
            'turns':[{'id':'new','status':'completed','startedAt':1791065505,'items':[
                {'type':'userMessage','id':'user-new','content':[{'type':'text','text':'现成任务稿'},{'type':'localImage','path':'private.png'}]},
                {'type':'commandExecution','command':'never executed by the importer'},
                {'type':'agentMessage','id':'msg-final','phase':'final_answer','text':'实际最终文字'}]},
                {'id':'old','status':'completed','items':[{'type':'agentMessage','id':'msg-old','phase':'commentary','text':'旧进度'}]}]}}

class SourceChecks(unittest.TestCase):
    def test_source_turn_order_roles_phase_and_missing_media_are_explicit(self):
        result=module.normalize(fixture())
        self.assertEqual([m['id'] for m in result['messages']],['msg-old','user-new','msg-final'])
        self.assertEqual(result['messages'][-1]['phase'],'final_answer')
        self.assertEqual(result['messages'][-1]['sourceMessageId'],'msg-final')
        self.assertIn('仅取得文字',result['messages'][1]['text'])
        self.assertNotIn('private.png',json.dumps(result))
        self.assertTrue(result['partial'])
        self.assertEqual(result['olderCursor'],'opaque-older')
        self.assertIn('来源摘要',result['coverage']['description'])

    def test_chatgpt_completed_reply_without_phase_is_preserved(self):
        data=fixture(); data['source']['thread']['kind']='chatgpt'
        data['source']['page']={'order':'oldest_first','hasMore':False,'nextCursor':None}
        data['source']['turns']=[{'id':'gpt-turn','status':'completed','items':[
            {'type':'userMessage','id':'gpt-turn','content':[{'type':'text','text':'问题'}]},
            {'type':'agentMessage','id':'gpt-answer','text':'实际答案','truncated':False}]}]
        result=module.normalize(data)
        self.assertEqual([m['role'] for m in result['messages']],['user','assistant'])
        self.assertNotIn('phase',result['messages'][1]); self.assertIsNone(result['olderCursor'])
        self.assertTrue(result['partial'])

    def test_wrong_thread_and_unverifiable_pagination_never_import(self):
        for mutate in [lambda d:d['source']['thread'].update(id=str(uuid.uuid4())),
                       lambda d:d['source'].update(page={}),
                       lambda d:d['source']['page'].update(nextCursor=None)]:
            data=fixture(); mutate(data)
            with self.assertRaises(WorkflowError): module.normalize(data)

    def test_long_source_text_is_flagged_and_stays_inside_backend_limit(self):
        data=fixture(); data['source']['turns'][0]['items'][-1]['text']='长'*21000
        result=module.normalize(data); message=result['messages'][-1]
        self.assertLessEqual(len(message['text']),20000); self.assertTrue(message['truncated'])
        self.assertIn('后续文字未获取',message['text'])

    def test_real_cli_import_writes_only_existing_private_cache_and_keeps_requests_separate(self):
        with tempfile.TemporaryDirectory(prefix='console-cache-import-') as temporary:
            directory=Path(temporary).resolve(); service=WorkflowService(directory,recover_jobs=False)
            service.conversations_catalog({'requestId':str(uuid.uuid4()),'fetchedAt':'2026-10-04T00:00:00Z','projects':[],
                'threads':[{'id':ID,'kind':'codex','title':'真实来源fixture','hostId':'local'}],'partial':True})
            pending=service.conversations_request({'requestId':str(uuid.uuid4()),'threadId':ID,'mode':'refresh'})['fetchRequest']
            data=fixture(); data['generation']=pending['generation']
            input_path=directory/'source.json'; input_path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            result=subprocess.run([sys.executable,'-B',str(path),'--data-dir',str(directory),'--json-file',str(input_path)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            cached=service.conversations_thread(ID)
            self.assertEqual(len(cached['messages']),3)
            self.assertEqual(service.incubator_dispatches()['dispatches'],[])
            self.assertEqual(service.conversations_fetch_requests()['requests'][0]['status'],'pending')

if __name__=='__main__': unittest.main()
