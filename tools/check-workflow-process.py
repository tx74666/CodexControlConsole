"""Real Windows task descendants; never enumerate or terminate user processes."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_process import WorkflowProcess
from workflow_service import WorkflowService


@unittest.skipUnless(os.name == 'nt', 'Windows job-object boundary')
class ProcessChecks(unittest.TestCase):
    def setUp(self):
        self.processes, self.child_handles = [], []
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL

    def tearDown(self):
        for process in self.processes:
            try:
                if isinstance(process, WorkflowProcess):
                    process.release()
                elif process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
            finally:
                if process.stdout:
                    process.stdout.close()
        for handle in self.child_handles:
            self.kernel.CloseHandle(handle)

    def start(self, script, *, owned=True, cwd=None, env=None):
        factory = WorkflowProcess if owned else subprocess.Popen
        process = factory([sys.executable, '-c', script], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        self.processes.append(process)
        return process

    def child(self, *, root_exits=False):
        code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True); "
        code += "sys.exit(0)" if root_exits else "time.sleep(60)"
        process = self.start(code)
        # The launcher prints only its child ID, which is bound to a kernel
        # handle before termination. No PID-based taskkill or global scan.
        pid = int(process.stdout.readline().decode('utf-8').strip())
        handle = self.kernel.OpenProcess(0x100000, False, pid)
        self.assertTrue(handle)
        self.child_handles.append(handle)
        return process, handle

    def test_terminate_ends_descendants_and_preserves_unrelated_owned_fixture(self):
        other = self.start('import time; time.sleep(60)', owned=False)
        process, handle = self.child()
        process.terminate()
        process.wait(timeout=5)
        self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
        self.assertIsNone(other.poll(), 'A separate task must remain alive.')

    def test_release_ends_child_after_launcher_exits_and_is_idempotent(self):
        process, handle = self.child(root_exits=True)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(self.kernel.WaitForSingleObject(handle, 0), 258)
        process.release()
        process.release()
        self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)

    def test_unicode_paths_environment_argv_and_redirected_io(self):
        with tempfile.TemporaryDirectory(prefix='console workflow 空格 ') as directory:
            script = 'import json,os,sys; print(json.dumps([os.getcwd(),os.environ["CONSOLE_TEST_VALUE"],sys.argv[1],sys.stdin.read()],ensure_ascii=False))'
            process = WorkflowProcess([sys.executable, '-c', script, 'literal ` $() " text'],
                                      cwd=directory, env={**os.environ, 'CONSOLE_TEST_VALUE': '文字=with value', 'PYTHONIOENCODING': 'utf-8'},
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            self.processes.append(process)
            output, _ = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
            result = json.loads(output.decode('utf-8'))
            self.assertEqual(Path(result[0]).resolve(), Path(directory).resolve())
            self.assertEqual(result[1:], ['文字=with value', 'literal ` $() " text', ''])

    def test_failed_creation_releases_private_job_and_starts_nothing(self):
        with tempfile.TemporaryDirectory(prefix='console-workflow-missing-') as directory:
            with self.assertRaises(OSError):
                WorkflowProcess([str(Path(directory) / 'does-not-exist.exe')],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def workflow_child(self, root, *, timeout):
        launcher = root / 'launcher.py'
        launcher.write_text('''import json,os,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
Path('child.pid.tmp').write_text(str(child.pid),encoding='ascii')
Path('child.pid.tmp').replace('child.pid')
while not Path('allow-return').exists():
    time.sleep(.01)
Path(os.environ['CONSOLE_WORKFLOW_RESULT_MANIFEST']).write_text(json.dumps({'text':'Launcher actually returned','files':[]}),encoding='utf-8')
print('launcher output',flush=True)
''', encoding='utf-8')
        service = WorkflowService(root / 'data', projects=[
            {'id': 'fixture', 'name': 'Isolated process fixture', 'root': str(root),
             'capabilities': ['command'], 'allowGeneratedScripts': False,
             'commands': [{'id': 'child', 'name': 'Owned child',
                           'argv': [sys.executable, str(launcher)], 'timeout': timeout}]}])
        service.start()
        try:
            record = service.create({'requestId': str(uuid.uuid4()), 'title': 'Owned child only', 'projectId': 'fixture'})['record']['id']
            job = service.submit({'requestId': str(uuid.uuid4()), 'recordId': record,
                                  'text': 'Run isolated owned child', 'action': 'command', 'commandId': 'child'})['job']
            deadline = time.monotonic() + 4
            while not (root / 'child.pid').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((root / 'child.pid').is_file())
            pid = int((root / 'child.pid').read_text(encoding='ascii'))
            handle = self.kernel.OpenProcess(0x100000, False, pid)
            self.assertTrue(handle)
            self.child_handles.append(handle)
            return service, record, job['id'], handle
        except BaseException:
            service.shutdown()
            raise

    def finished(self, service, record, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = next(item for item in service.detail(record)['jobs'] if item['id'] == job_id)
            if result['status'] in {'succeeded', 'failed', 'interrupted'}:
                return result
            time.sleep(.02)
        self.fail('Owned workflow fixture did not become terminal.')

    def test_workflow_success_releases_lingering_child_before_preserving_stdout(self):
        with tempfile.TemporaryDirectory(prefix='console-workflow-success-') as directory:
            root = Path(directory)
            service, record, job, handle = self.workflow_child(root, timeout=5)
            try:
                (root / 'allow-return').write_text('return', encoding='ascii')
                result = self.finished(service, record, job)
                self.assertEqual(result['status'], 'succeeded')
                self.assertIn('launcher output', result['log'])
                self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                service.shutdown()

    def test_workflow_timeout_ends_owned_tree_and_retains_failed_attempt(self):
        with tempfile.TemporaryDirectory(prefix='console-workflow-timeout-') as directory:
            service, record, job, handle = self.workflow_child(Path(directory), timeout=2)
            try:
                result = self.finished(service, record, job)
                self.assertEqual(result['status'], 'failed')
                self.assertIn('超时', result['error'])
                self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
                self.assertEqual(len(service.detail(record)['jobs']), 1)
            finally:
                service.shutdown()

    def test_workflow_shutdown_ends_owned_tree_and_records_interruption(self):
        with tempfile.TemporaryDirectory(prefix='console-workflow-shutdown-') as directory:
            service, record, job, handle = self.workflow_child(Path(directory), timeout=5)
            try:
                service.shutdown()
                result = self.finished(service, record, job)
                self.assertEqual(result['status'], 'interrupted')
                self.assertEqual(self.kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                service.shutdown()

    def test_reader_start_failure_still_releases_the_actual_owned_process(self):
        import threading
        with tempfile.TemporaryDirectory(prefix='console-workflow-reader-failure-') as directory:
            root, captured = Path(directory), []
            service = WorkflowService(root / 'data', projects=[
                {'id': 'fixture', 'name': 'Reader failure fixture', 'root': str(root),
                 'capabilities': ['command'], 'allowGeneratedScripts': False,
                 'commands': [{'id': 'sleep', 'name': 'Owned sleeper',
                               'argv': [sys.executable, '-c', 'import time; time.sleep(60)'], 'timeout': 5}]}])
            original_start = threading.Thread.start
            def start(thread):
                if thread.name == 'workflow-output-reader':
                    raise RuntimeError('Controlled reader-start failure')
                return original_start(thread)
            def process(*args, **kwargs):
                result = WorkflowProcess(*args, **kwargs)
                captured.append(result)
                return result
            try:
                with patch('workflow_service.WorkflowProcess', side_effect=process), patch.object(threading.Thread, 'start', start):
                    service.start()
                    record = service.create({'requestId': str(uuid.uuid4()), 'title': 'Reader failure', 'projectId': 'fixture'})['record']['id']
                    job = service.submit({'requestId': str(uuid.uuid4()), 'recordId': record, 'text': 'Owned sleeper only', 'action': 'command', 'commandId': 'sleep'})['job']['id']
                    self.assertEqual(self.finished(service, record, job)['status'], 'failed')
                    self.assertEqual(len(captured), 1)
                    self.assertIsNotNone(captured[0].poll())
                    self.assertTrue(captured[0].stdout.closed)
                    self.assertIsNone(service._process)
            finally:
                service.shutdown()


if __name__ == '__main__':
    unittest.main(verbosity=2)
