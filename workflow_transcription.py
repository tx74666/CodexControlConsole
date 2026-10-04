"""Local Windows recording transcription; never contacts a model service.

Only an already saved, bounded recording is read. The installed Windows desktop
recognizer runs in a private WorkflowProcess job; it never opens a microphone.
Compressed recordings use an existing ffmpeg executable, without downloading one.
System.Speech file input: https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.setinputtowavefile
"""
from __future__ import annotations

import base64
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid
import wave

from workflow_process import WorkflowProcess

MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_AUDIO_SECONDS = 180
MAX_PROCESS_OUTPUT = 256 * 1024
_cache_lock = threading.Lock()
_capability_cache = None


class LocalTranscriptionError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _fail(code, message, status=400):
    raise LocalTranscriptionError(code, message, status)


def _safe_path(value, *, file=False):
    path = Path(value)
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        _fail("invalid_path", "录音和任务目录必须是本机绝对路径。", 403)
    if os.name == "nt" and any(":" in part for part in path.parts[1:]):
        _fail("invalid_path", "录音路径不能使用备用数据流。", 403)
    for item in (path, *path.parents):
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(metadata, "st_file_attributes", 0) & 0x400:
            _fail("invalid_path", "录音和任务目录不能使用链接或重解析路径。", 403)
    path = path.resolve()
    if file and (not path.is_file() or not 0 < path.stat().st_size <= MAX_AUDIO_BYTES):
        _fail("invalid_audio", "录音文件不存在、为空或超过 12 MB。")
    return path


def _powershell():
    if os.name != "nt":
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if not 0 < count < len(buffer):
        return None
    candidate = Path(buffer.value) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        path = _safe_path(candidate)
        return path if path.is_file() else None
    except (LocalTranscriptionError, OSError):
        return None


def _find_ffmpeg(path=None):
    candidate = path or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not candidate:
        return None
    try:
        result = _safe_path(candidate)
        return result if result.is_file() and result.suffix.lower() == ".exe" else None
    except (LocalTranscriptionError, OSError, TypeError):
        return None


def _installed_languages():
    if os.name != "nt":
        return []
    import winreg
    languages = set()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Recognizers\Tokens",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            for index in range(min(winreg.QueryInfoKey(key)[0], 64)):
                token = winreg.EnumKey(key, index)
                try:
                    with winreg.OpenKey(key, token + r"\Attributes") as attributes:
                        language = winreg.QueryValueEx(attributes, "Language")[0]
                    for value in str(language).split(";"):
                        locale = {0x804: "zh-CN", 0x409: "en-US"}.get(int(value, 16))
                        if locale:
                            languages.add(locale)
                except (OSError, ValueError):
                    continue
    except OSError:
        pass
    return sorted(languages)


def local_transcription_config(ffmpeg_path=None):
    """Cheap capability discovery; no processes, audio, secret reads or installs."""
    global _capability_cache
    with _cache_lock:
        now = time.monotonic()
        ffmpeg = _find_ffmpeg(ffmpeg_path)
        cache_key = str(ffmpeg) if ffmpeg else ""
        if _capability_cache and now - _capability_cache[0] < 30 and _capability_cache[2] == cache_key:
            return {**_capability_cache[1], "languages": list(_capability_cache[1]["languages"])}
        languages = _installed_languages()
        available = bool(_powershell() and languages)
        value = {"provider": "windows_local", "available": available,
                 "status": "ready" if available else "missing_config", "languages": languages,
                 "compressedAudioAvailable": bool(ffmpeg),
                 "reason": "" if available else "此电脑没有可用的 Windows 中文或英文语音识别组件；仍可使用手机键盘听写。"}
        _capability_cache = now, value, cache_key
        return {**value, "languages": list(languages)}


# No recording names or content are substituted into executable PowerShell text.
# The JSON file is data; the helper recognizes a WAV file, never a live device.
_SPEECH_SCRIPT = r'''$InputJson = [Environment]::GetEnvironmentVariable('CONSOLE_LOCAL_TRANSCRIPTION_INPUT')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Speech
    Add-Type -ReferencedAssemblies @('System.Speech', 'System', 'System.Core') -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.Recognition;
using System.Threading;
public class ConsoleLocalSpeechResult {
    public string Text;
    public double[] Confidences;
    public int RejectedSegments;
}
public static class ConsoleLocalSpeech {
    public static ConsoleLocalSpeechResult Run(string path, string language, int timeout) {
        var phrases = new List<string>();
        var confidence = new List<double>();
        Exception error = null;
        int rejected = 0;
        using (var completed = new ManualResetEvent(false))
        using (var engine = new SpeechRecognitionEngine(new System.Globalization.CultureInfo(language))) {
            engine.LoadGrammar(new DictationGrammar());
            engine.SetInputToWaveFile(path);
            engine.SpeechRecognized += delegate(object sender, SpeechRecognizedEventArgs e) {
                if (e.Result != null && !String.IsNullOrWhiteSpace(e.Result.Text)) {
                    phrases.Add(e.Result.Text); confidence.Add(e.Result.Confidence);
                }
            };
            engine.SpeechRecognitionRejected += delegate { rejected++; };
            engine.RecognizeCompleted += delegate(object sender, RecognizeCompletedEventArgs e) {
                error = e.Error; completed.Set();
            };
            engine.RecognizeAsync(RecognizeMode.Multiple);
            if (!completed.WaitOne(timeout)) {
                engine.RecognizeAsyncCancel();
                throw new TimeoutException("Recognition timed out.");
            }
            if (error != null) throw error;
        }
        return new ConsoleLocalSpeechResult { Text = String.Join("\n", phrases),
            Confidences = confidence.ToArray(), RejectedSegments = rejected };
    }
}
'@
    $request = [System.IO.File]::ReadAllText($InputJson, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $result = [ConsoleLocalSpeech]::Run([string]$request.path, [string]$request.language, [int]$request.timeoutMs)
    @{ok=$true; text=$result.Text; confidences=$result.Confidences; rejectedSegments=$result.RejectedSegments} | ConvertTo-Json -Depth 4 -Compress
} catch {
    $failure = $_.Exception.GetBaseException()
    $code = if ($failure -is [System.TimeoutException]) { 'transcription_timeout' } else { 'local_recognizer_failed' }
    @{ok=$false; code=$code} | ConvertTo-Json -Compress
    exit 2
}
'''


def _run_owned(argv, directory, log_path, deadline, stop_event=None, *, env=None):
    process = None
    if stop_event is not None and stop_event.is_set():
        _fail("interrupted", "本机录音转写已停止；原录音已保留。", 503)
    if time.monotonic() >= deadline:
        _fail("transcription_timeout", "本机录音转写超时；原录音已保留。", 504)
    with log_path.open("xb") as output:
        try:
            try:
                process = WorkflowProcess([str(item) for item in argv], cwd=str(directory), env=env,
                                          stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except OSError:
                _fail("missing_config", "电脑无法启动本机语音组件；原录音已保留。", 503)
            while process.poll() is None:
                if stop_event is not None and stop_event.is_set():
                    _fail("interrupted", "本机录音转写已停止；原录音已保留。", 503)
                if time.monotonic() >= deadline:
                    _fail("transcription_timeout", "本机录音转写超时；原录音已保留，可明确重试。", 504)
                if log_path.stat().st_size > MAX_PROCESS_OUTPUT:
                    _fail("transcription_failed", "语音组件返回内容超过限制；原录音已保留。", 502)
                time.sleep(0.1)
            code = process.returncode
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)
                finally:
                    process.release()
    if log_path.stat().st_size > MAX_PROCESS_OUTPUT:
        _fail("transcription_failed", "语音组件返回内容超过限制。", 502)
    return code, log_path.read_text(encoding="utf-8-sig", errors="replace")


def _audio_format(path):
    with path.open("rb") as source:
        header = source.read(64)
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "matroska"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "mov"
    if header.startswith(b"ID3") or len(header) >= 2 and header[0] == 255 and header[1] & 0xE0 == 0xE0:
        return "mp3"
    _fail("unsupported_audio", "请选择有效 WAV、M4A、MP3、WebM 或 OGG 录音。", 415)


def _wav_info(path):
    try:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            duration = source.getnframes() / rate
            expected = source.getnframes() * source.getnchannels() * source.getsampwidth()
            if expected > MAX_AUDIO_BYTES or len(source.readframes(source.getnframes())) != expected:
                _fail("invalid_audio", "WAV 录音的数据长度与声明不一致。")
            direct = (source.getcomptype() == "NONE" and source.getnchannels() in {1, 2}
                      and source.getsampwidth() in {1, 2} and 8000 <= rate <= 48000)
    except (wave.Error, EOFError, ZeroDivisionError, OSError):
        return None, False
    if not math.isfinite(duration) or duration <= 0:
        _fail("invalid_audio", "录音没有有效声音时长。")
    if duration > MAX_AUDIO_SECONDS:
        _fail("audio_too_long", "录音不能超过三分钟；没有截断或执行任务。", 413)
    return duration, direct


def local_transcribe(input_path, job_dir, *, stop_event=None, progress_callback=None,
                     locale="zh-CN", ffmpeg_path=None, timeout_seconds=240):
    """Return editable transcript metadata, without dispatching or running a task."""
    if stop_event is not None and stop_event.is_set():
        _fail("interrupted", "本机录音转写已停止。", 503)
    source = _safe_path(input_path, file=True)
    directory = _safe_path(job_dir)
    if directory == source or directory in source.parents:
        _fail("invalid_path", "原录音必须独立于转写任务输出目录。", 403)
    audio_format = _audio_format(source)
    duration, direct = _wav_info(source) if audio_format == "wav" else (None, False)
    config = local_transcription_config(ffmpeg_path)
    if not config["available"] or locale not in config["languages"]:
        _fail("missing_config", "此电脑没有所选语言的 Windows 语音识别组件；可使用手机键盘听写。", 503)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 300:
        _fail("invalid_input", "本机转写等待时间须在 1 至 300 秒以内。")
    deadline = time.monotonic() + timeout_seconds
    directory.mkdir(parents=True, exist_ok=True)
    directory = _safe_path(directory)
    run_dir = directory / ("transcription-" + uuid.uuid4().hex)
    run_dir.mkdir(mode=0o700)
    run_dir = _safe_path(run_dir)

    def progress(message):
        if progress_callback is not None:
            progress_callback(message)

    normalized = run_dir / "recording.wav"
    try:
        if not direct:
            ffmpeg = _find_ffmpeg(ffmpeg_path)
            if ffmpeg is None:
                _fail("missing_config", "此录音格式需要电脑已有的 ffmpeg；原录音已保留，也可使用手机键盘听写。", 503)
            progress("正在本机转换录音格式，不上传到 AI 服务。")
            source = _safe_path(source, file=True)
            argv = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file",
                    "-f", audio_format]
            if audio_format == "mov":
                argv += ["-enable_drefs", "0"]
            argv += ["-i", source, "-map", "0:a:0", "-vn", "-sn", "-dn", "-t", "180.05",
                     "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", normalized]
            code, _ = _run_owned(argv, run_dir, run_dir / "decode.log", min(deadline, time.monotonic() + 45), stop_event)
            if code != 0 or not normalized.is_file():
                _fail("invalid_audio", "电脑无法解码此录音；原文件已保留。")
            source = _safe_path(normalized, file=True)
            duration, direct = _wav_info(source)
            if duration is None or not direct:
                _fail("invalid_audio", "转换后的录音格式无效。")
        progress("正在使用 Windows 本机语音识别，转写完成后请检查文字。")
        source = _safe_path(source, file=True)
        script = run_dir / "speech.ps1"
        script.write_text(_SPEECH_SCRIPT, encoding="utf-8-sig")
        request = run_dir / "input.json"
        request.write_text(json.dumps({"path": str(source), "language": locale,
                                      "timeoutMs": max(1, int((deadline - time.monotonic()) * 1000))}, ensure_ascii=False), encoding="utf-8")
        # Windows may forbid .ps1 files while permitting ordinary commands. Run
        # this module's fixed command, with no execution-policy change or data
        # interpolation; retain the identical private script for diagnostics.
        command = base64.b64encode(_SPEECH_SCRIPT.encode("utf-16le")).decode("ascii")
        powershell = _powershell()
        if powershell is None:
            _fail("missing_config", "电脑没有可用的 Windows 语音组件运行程序；原录音已保留。", 503)
        code, output = _run_owned([powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-EncodedCommand", command],
                                  run_dir, run_dir / "recognition.log", deadline, stop_event,
                                  env={**os.environ, "CONSOLE_LOCAL_TRANSCRIPTION_INPUT": str(request),
                                       "TEMP": str(run_dir), "TMP": str(run_dir)})
        try:
            result = json.loads(output)
        except ValueError:
            _fail("transcription_failed", "Windows 语音组件没有返回有效结果；原录音已保留。", 502)
        if code != 0 or result.get("ok") is not True:
            if result.get("code") == "transcription_timeout":
                _fail("transcription_timeout", "Windows 本机语音转写超时；原录音已保留，可明确重试。", 504)
            _fail("missing_config", "Windows 本机语音组件无法识别此录音；原录音已保留，可使用手机键盘听写。", 503)
        text = result.get("text", "")
        if not isinstance(text, str) or len(text) > 50000 or "\x00" in text:
            _fail("transcription_failed", "Windows 语音转写文字无效。", 502)
        if not text.strip():
            _fail("no_speech", "这段录音没有识别出文字；原录音已保留，请重新录音或使用手机键盘听写。", 422)
        return {"text": text.strip(), "provider": "windows_local", "language": locale,
                "durationValidated": True, "durationSeconds": duration,
                "confidences": result.get("confidences", []), "rejectedSegments": result.get("rejectedSegments", 0),
                "reviewRequired": True}
    finally:
        # Decode failures can leave an empty copy in this unique, verified job child.
        if normalized.exists():
            decoded = _safe_path(normalized)
            if decoded.parent != run_dir or not decoded.is_file():
                _fail("invalid_path", "转写临时录音路径无效。", 403)
            decoded.unlink()
