"""Launch only Console-owned processes and contain their Windows descendants.

Job assignment is part of CreateProcess, before executable code can run:
https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812
The job is private and non-inheritable; closing it terminates its members.
This is lifetime management, not a filesystem or permission sandbox.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading


if os.name == 'nt':
    import ctypes
    from ctypes import wintypes as w

    class _BasicLimits(ctypes.Structure):
        _fields_ = [('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSet', ctypes.c_size_t),
                    ('MaximumWorkingSet', ctypes.c_size_t), ('ActiveProcesses', w.DWORD),
                    ('Affinity', ctypes.c_size_t), ('Priority', w.DWORD), ('Scheduling', w.DWORD)]

    class _IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('ReadOperations', 'WriteOperations', 'OtherOperations',
                     'ReadBytes', 'WriteBytes', 'OtherBytes')]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [('Basic', _BasicLimits), ('IO', _IOCounters),
                    ('ProcessMemory', ctypes.c_size_t), ('JobMemory', ctypes.c_size_t),
                    ('PeakProcessMemory', ctypes.c_size_t), ('PeakJobMemory', ctypes.c_size_t)]

    class _StartupInfo(ctypes.Structure):
        _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
                    ('title', w.LPWSTR), ('x', w.DWORD), ('y', w.DWORD),
                    ('width', w.DWORD), ('height', w.DWORD), ('xchars', w.DWORD),
                    ('ychars', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
                    ('show', w.WORD), ('reserved_size', w.WORD),
                    ('reserved_bytes', ctypes.POINTER(w.BYTE)),
                    ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]

    class _StartupInfoEx(ctypes.Structure):
        _fields_ = [('startup', _StartupInfo), ('attributes', ctypes.c_void_p)]

    class _ProcessInfo(ctypes.Structure):
        _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE),
                    ('pid', w.DWORD), ('tid', w.DWORD)]

    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    def _bind(name, result, *arguments):
        function = getattr(_kernel, name)
        function.restype, function.argtypes = result, list(arguments)
        return function

    _create_job = _bind('CreateJobObjectW', w.HANDLE, ctypes.c_void_p, w.LPCWSTR)
    _set_job = _bind('SetInformationJobObject', w.BOOL, w.HANDLE, ctypes.c_int,
                     ctypes.c_void_p, w.DWORD)
    _terminate_job = _bind('TerminateJobObject', w.BOOL, w.HANDLE, w.UINT)
    _close_handle = _bind('CloseHandle', w.BOOL, w.HANDLE)
    _init_attributes = _bind('InitializeProcThreadAttributeList', w.BOOL,
                             ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t))
    _update_attribute = _bind('UpdateProcThreadAttribute', w.BOOL, ctypes.c_void_p,
                              w.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                              ctypes.c_void_p, ctypes.c_void_p)
    _delete_attributes = _bind('DeleteProcThreadAttributeList', None, ctypes.c_void_p)
    _create_process = _bind('CreateProcessW', w.BOOL, w.LPCWSTR, w.LPWSTR,
                            ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                            ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(_StartupInfoEx),
                            ctypes.POINTER(_ProcessInfo))

    def _check(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def _new_job():
        handle = _check(_create_job(None, None))
        limits = _ExtendedLimits()
        limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            _check(_set_job(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            return handle
        except BaseException:
            _close_handle(handle)
            raise

    def _start_in_job(job, argv, executable, cwd, environment, std_handles, flags):
        size = ctypes.c_size_t()
        _init_attributes(None, 2, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        _check(_init_attributes(attributes, 2, 0, ctypes.byref(size)))
        # CPython has prepared inheritable child pipe handles. Pass only these
        # handles, never the job itself or any other application's handle.
        handles = (w.HANDLE * len(set(std_handles)))(*dict.fromkeys(std_handles))
        jobs = (w.HANDLE * 1)(job)
        try:
            _check(_update_attribute(attributes, 0, 0x00020002, handles,
                                     ctypes.sizeof(handles), None, None))
            _check(_update_attribute(attributes, 0, 0x0002000D, jobs,
                                     ctypes.sizeof(jobs), None, None))
            startup = _StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = std_handles
            startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            # Preserve the supplied environment including empty values; never
            # use a shell or interpolate task text into the command line.
            values = {os.fsdecode(key): os.fsdecode(value) for key, value in environment.items()}
            if any('\0' in key or '\0' in value or '=' in key for key, value in values.items()):
                raise ValueError('Invalid process environment.')
            environment_block = ctypes.create_unicode_buffer(
                '\0'.join(key + '=' + values[key] for key in sorted(values, key=str.upper)) + '\0\0')
            info = _ProcessInfo()
            sys.audit('subprocess.Popen', executable, argv, cwd, environment)
            _check(_create_process(executable, command_line, None, None, True,
                                   flags | 0x00080000 | 0x00000400,
                                   environment_block, cwd, ctypes.byref(startup), ctypes.byref(info)))
            _close_handle(info.thread)
            return info.process, info.pid
        finally:
            _delete_attributes(attributes)


class WorkflowProcess(subprocess.Popen):
    """Popen contract with a separate lifetime boundary for this task only."""
    def __init__(self, *args, **kwargs):
        self._job_lock = threading.RLock()
        self._workflow_job = _new_job() if os.name == 'nt' else None
        try:
            super().__init__(*args, **kwargs)
        except BaseException:
            self.release()
            raise

    def _execute_child(self, args, executable, preexec_fn, close_fds, pass_fds,
                       cwd, env, startupinfo, creationflags, shell,
                       p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite,
                       *platform_options):
        # CPython 3.12+ Windows Popen's pipe creation/wait/poll/handle ownership
        # remain unchanged. Only its process creation step gains job attributes.
        if os.name != 'nt':
            return super()._execute_child(args, executable, preexec_fn, close_fds,
                                          pass_fds, cwd, env, startupinfo, creationflags,
                                          shell, p2cread, p2cwrite, c2pread, c2pwrite,
                                          errread, errwrite, *platform_options)
        try:
            if shell or preexec_fn or pass_fds or startupinfo is not None:
                raise ValueError('Workflow processes require explicit argv without shell or custom startup handles.')
            if not isinstance(args, (list, tuple)) or not args or any(not isinstance(arg, str) for arg in args):
                raise ValueError('Workflow process argv is invalid.')
            if -1 in (p2cread, c2pwrite, errwrite):
                raise ValueError('Workflow processes require redirected input and output.')
            process_handle, pid = _start_in_job(self._workflow_job, args,
                                                os.fsdecode(executable or args[0]),
                                                os.fsdecode(cwd) if cwd is not None else None,
                                                os.environ if env is None else env,
                                                tuple(map(int, (p2cread, c2pwrite, errwrite))), creationflags)
            self._child_created = True
            self._handle = subprocess.Handle(process_handle)
            self.pid = pid
        finally:
            self._close_pipe_fds(p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite)

    def terminate(self):
        if os.name == 'nt':
            with self._job_lock:
                if self._workflow_job is not None:
                    _check(_terminate_job(self._workflow_job, 1))
            return
        return super().terminate()

    kill = terminate

    def release(self):
        """Close this private job, also ending descendants after root exit."""
        if os.name == 'nt':
            with self._job_lock:
                handle, self._workflow_job = self._workflow_job, None
                if handle is not None:
                    _check(_close_handle(handle))
