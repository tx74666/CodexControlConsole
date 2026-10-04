"""Isolated local speech checks; synthetic speech is not an iPhone/user test."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workflow_transcription as transcription
from workflow_process import WorkflowProcess


def silent_wav(path, seconds=1):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * int(seconds * 16000))


class TranscriptionChecks(unittest.TestCase):
    def test_capability_discovery_is_cached_and_never_starts_a_process(self):
        with patch.object(transcription, "_capability_cache", None), patch.object(transcription, "WorkflowProcess", side_effect=AssertionError("No process during config")), patch.object(transcription, "_installed_languages", return_value=["zh-CN"]) as discovery, patch.object(transcription, "_powershell", return_value=Path("installed.exe")), patch.object(transcription, "_find_ffmpeg", return_value=None):
            first = transcription.local_transcription_config()
            first["languages"].append("private mutation")
            self.assertEqual(transcription.local_transcription_config()["languages"], ["zh-CN"])
            self.assertEqual(discovery.call_count, 1)

    def test_explicit_installed_decoder_updates_cached_capability_without_processes(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-decoder-discovery-") as directory:
            candidate = Path(directory) / "trusted-discovery.exe"
            candidate.write_bytes(b"already installed fixture")
            with patch.object(transcription, "_capability_cache", None), patch.object(transcription, "WorkflowProcess", side_effect=AssertionError("No process during config")), patch.object(transcription, "_installed_languages", return_value=["zh-CN"]) as discovery, patch.object(transcription, "_powershell", return_value=Path("installed.exe")), patch.object(transcription.shutil, "which", return_value=None):
                self.assertFalse(transcription.local_transcription_config()["compressedAudioAvailable"])
                self.assertTrue(transcription.local_transcription_config(candidate)["compressedAudioAvailable"])
                self.assertTrue(transcription.local_transcription_config(candidate)["compressedAudioAvailable"])
                self.assertEqual(discovery.call_count, 2)

    def test_recognizer_internal_timeout_is_not_reported_as_missing_configuration(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-timeout-result-") as directory:
            root = Path(directory)
            source = root / "silence.wav"
            silent_wav(source)
            with patch.object(transcription, "local_transcription_config", return_value={"available": True, "languages": ["zh-CN"]}), patch.object(transcription, "_powershell", return_value=Path("installed.exe")), patch.object(transcription, "_run_owned", return_value=(2, '{"ok":false,"code":"transcription_timeout"}')):
                with self.assertRaises(transcription.LocalTranscriptionError) as error:
                    transcription.local_transcribe(source, root / "job")
                self.assertEqual(error.exception.code, "transcription_timeout")

    def test_three_minute_limit_rejects_original_without_creating_outputs(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-bound-") as directory:
            root = Path(directory)
            source = root / "too-long.wav"
            silent_wav(source, 180.01)
            with self.assertRaises(transcription.LocalTranscriptionError) as error:
                transcription.local_transcribe(source, root / "job")
            self.assertEqual(error.exception.code, "audio_too_long")
            self.assertFalse((root / "job").exists())

    def test_cancellation_leaves_recording_unchanged(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(transcription.LocalTranscriptionError) as error:
            transcription.local_transcribe("not read", "not created", stop_event=event)
        self.assertEqual(error.exception.code, "interrupted")

    def test_link_input_and_output_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-links-") as directory:
            root = Path(directory)
            source = root / "source.wav"
            silent_wav(source)
            link = root / "linked.wav"
            try:
                link.symlink_to(source)
            except OSError:
                self.skipTest("Symlink creation not granted on this test host")
            with self.assertRaises(transcription.LocalTranscriptionError) as error:
                transcription.local_transcribe(link, root / "job")
            self.assertEqual(error.exception.code, "invalid_path")

    def test_wave_duration_requires_matching_actual_frame_data(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-truncated-") as directory:
            root = Path(directory)
            source = root / "truncated.wav"
            silent_wav(source)
            source.write_bytes(source.read_bytes()[:-8])
            with self.assertRaises(transcription.LocalTranscriptionError) as error:
                transcription.local_transcribe(source, root / "job")
            self.assertEqual(error.exception.code, "invalid_audio")
            self.assertFalse((root / "job").exists())

    def test_owned_process_timeout_and_cancellation_close_its_private_job(self):
        with tempfile.TemporaryDirectory(prefix="console-speech-process-") as directory:
            root = Path(directory)
            for cancelled in (False, True):
                event, captured = threading.Event(), []
                original = transcription.WorkflowProcess
                def create(*args, **kwargs):
                    process = original(*args, **kwargs)
                    captured.append(process)
                    if cancelled:
                        event.set()
                    return process
                with patch.object(transcription, "WorkflowProcess", side_effect=create):
                    with self.assertRaises(transcription.LocalTranscriptionError) as error:
                        transcription._run_owned([sys.executable, "-c", "import time; time.sleep(60)"], root,
                                                 root / ("cancel.log" if cancelled else "timeout.log"), time.monotonic() + .3, event)
                self.assertEqual(error.exception.code, "interrupted" if cancelled else "transcription_timeout")
                self.assertEqual(len(captured), 1)
                self.assertIsNotNone(captured[0].poll())
                if os.name == "nt":
                    self.assertIsNone(captured[0]._workflow_job)

    @unittest.skipUnless(os.name == "nt", "Installed Windows recognizer and ffmpeg")
    def test_compressed_long_audio_is_rejected_instead_of_truncated(self):
        ffmpeg = transcription._find_ffmpeg()
        if not ffmpeg or not transcription.local_transcription_config()["available"]:
            self.skipTest("Windows recognizer or ffmpeg is unavailable")
        with tempfile.TemporaryDirectory(prefix="console-speech-long-compressed-") as directory:
            root = Path(directory)
            source, compressed = root / "long.wav", root / "long.m4a"
            silent_wav(source, 181)
            code, _ = transcription._run_owned([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", source,
                                                "-c:a", "aac", compressed], root, root / "encode.log", time.monotonic() + 20)
            self.assertEqual(code, 0)
            before = compressed.read_bytes()
            with self.assertRaises(transcription.LocalTranscriptionError) as error:
                transcription.local_transcribe(compressed, root / "job", timeout_seconds=30)
            self.assertEqual(error.exception.code, "audio_too_long")
            self.assertEqual(compressed.read_bytes(), before)
            self.assertEqual(list((root / "job").rglob("recording.wav")), [])

    @unittest.skipUnless(os.name == "nt", "Installed Windows recognizer")
    def test_real_silence_has_no_invented_transcript(self):
        config = transcription.local_transcription_config()
        if not config["available"]:
            self.skipTest("Windows recognizer is not installed")
        with tempfile.TemporaryDirectory(prefix="console-speech-silence-") as directory:
            root = Path(directory)
            source = root / "silence.wav"
            silent_wav(source)
            before = source.read_bytes()
            with self.assertRaises(transcription.LocalTranscriptionError) as error:
                transcription.local_transcribe(source, root / "job", locale=config["languages"][0], timeout_seconds=30)
            self.assertEqual(error.exception.code, "no_speech")
            self.assertEqual(source.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "Installed Windows recognizer and TTS")
    def test_actual_synthetic_chinese_audio_and_compressed_copy(self):
        config = transcription.local_transcription_config()
        if "zh-CN" not in config["languages"]:
            self.skipTest("Chinese recognizer is not installed")
        with tempfile.TemporaryDirectory(prefix="console-speech-synthetic-") as directory:
            root = Path(directory)
            source = root / '合成声音 ` $() literal.wav'
            request = root / "tts-input.json"
            phrase = "请把这张图片发送到手机，我要查看结果。"
            request.write_text(json.dumps({"path": str(source), "text": phrase}, ensure_ascii=False), encoding="utf-8")
            script = root / "tts.ps1"
            script.write_text(r'''$InputJson=[Environment]::GetEnvironmentVariable('CONSOLE_LOCAL_TRANSCRIPTION_INPUT')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName System.Speech
$request=[IO.File]::ReadAllText($InputJson,[Text.Encoding]::UTF8) | ConvertFrom-Json
$synth=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $voice=$synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN' } | Select-Object -First 1
    if (-not $voice) { exit 17 }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.SetOutputToWaveFile([string]$request.path)
    $synth.Speak([string]$request.text)
} finally { $synth.Dispose() }
''', encoding="utf-8-sig")
            command = base64.b64encode(script.read_text(encoding="utf-8-sig").encode("utf-16le")).decode("ascii")
            process = WorkflowProcess([str(transcription._powershell()), "-NoLogo", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-EncodedCommand", command], cwd=root,
                                      env={**os.environ, "CONSOLE_LOCAL_TRANSCRIPTION_INPUT": str(request)},
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                output, _ = process.communicate(timeout=30)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                process.release()
            if process.returncode == 17:
                self.skipTest("Chinese synthetic voice is not installed")
            self.assertEqual(process.returncode, 0, output.decode("utf-8", errors="replace"))
            result = transcription.local_transcribe(source, root / "wav-job", timeout_seconds=60)
            self.assertTrue(result["text"].strip())
            self.assertTrue(result["durationValidated"])
            self.assertTrue(result["reviewRequired"])
            self.assertGreaterEqual(sum(word in result["text"] for word in ("图片", "手机", "结果")), 2, result["text"])
            print(json.dumps({"source": "synthetic Windows TTS, not real user speech", "expected": phrase,
                              "recognized": result["text"], "durationSeconds": result["durationSeconds"]}, ensure_ascii=True))
            ffmpeg = transcription._find_ffmpeg()
            if ffmpeg is None:
                return
            compressed = root / "synthetic.m4a"
            process = WorkflowProcess([str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(source), "-c:a", "aac", str(compressed)], cwd=root,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                output, _ = process.communicate(timeout=20)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                process.release()
            self.assertEqual(process.returncode, 0, output.decode("utf-8", errors="replace"))
            compressed_result = transcription.local_transcribe(compressed, root / "m4a-job", timeout_seconds=60)
            self.assertTrue(compressed_result["text"].strip())
            self.assertGreaterEqual(sum(word in compressed_result["text"] for word in ("图片", "手机", "结果")), 2, compressed_result["text"])
            self.assertEqual(list((root / "m4a-job").rglob("recording.wav")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
