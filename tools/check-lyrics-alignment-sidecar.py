"""Execute candidate functions in artifact-only fixtures; never import/start the Console app."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "world_console.py"
FUNCTIONS = {
    "file_sha256", "music_relative_path", "normalize_lyrics_language", "parse_lrc_timestamp",
    "parsed_timed_lyrics", "ensure_music_analysis_dir", "music_analysis_cache_path",
    "music_analysis_cache_meta", "read_music_analysis_cache", "write_music_analysis_cache",
    "invalidate_music_analysis_cache", "lyrics_word_tokens", "clamp_number",
    "music_alignment_sidecar_path", "validate_music_alignment_variant",
    "read_music_alignment_sidecar", "has_acoustic_alignment", "music_lyrics_analysis",
}


class AlignmentSidecarTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="alignment-fixture-", dir=ROOT))
        assert self.root.resolve().is_relative_to(ROOT.resolve())
        self.music = self.root / "music"
        self.music.mkdir()
        self.audio = self.music / "example.mp3"
        self.audio.write_bytes(b"fixture audio bytes, not a decoded audio file")
        self.lyrics = {"": self.music / "example.lrc", "en": self.music / "example.en.lrc",
                       "zh": self.music / "example.zh.lrc"}
        for language, path in self.lyrics.items():
            text = "[00:01.000]Hello, world\n[00:04.000]Again now\n[00:08.000]\n"
            if language == "zh":
                text = "[00:01.000]你好 世界\n[00:04.000]再次 此刻\n[00:08.000]\n"
            path.write_text(text, encoding="utf-8")
        self.marks = [{"lineIndex": 0, "boundaryIndex": 0, "role": "start", "time": 1.25}]
        self.decode_calls = 0

        def decoded(_path):
            self.decode_calls += 1
            return {"duration": 10.0, "hopSeconds": 0.015, "sampleRate": 8000,
                    "rms": [], "flux": [], "articulation": [], "speechFlow": []}

        self.ns = {"Path": Path, "copy": copy, "hashlib": hashlib, "json": json, "math": math,
                   "re": re, "datetime": datetime, "timezone": timezone,
                   "MUSIC_DIR": self.music, "MUSIC_ANALYSIS_DIR": self.root / "cache/music_analysis",
                   "LYRICS_LANGUAGE_ORDER": ("en", "zh", "fr"),
                   "music_path_from_relative": lambda _relative: self.audio,
                   "lyrics_path_from_music_path": lambda _audio, language="": self.lyrics.get(language),
                   "music_lyric_marks_for_path": lambda _audio: copy.deepcopy(self.marks),
                   "decoded_music_flux": decoded, "lyrics_waveform_window": lambda *args: []}
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
        assert {node.name for node in nodes} == FUNCTIONS
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), self.ns)
        self.sidecar = self.ns["music_alignment_sidecar_path"](self.audio)
        self.sidecar.parent.mkdir(parents=True)
        self.body = {"format": 1, "audioSha256": self.ns["file_sha256"](self.audio),
                     "variants": [self.variant(language) for language in self.lyrics]}
        self.write_sidecar()

    def tearDown(self):
        assert self.root.resolve().is_relative_to(ROOT.resolve())
        shutil.rmtree(self.root)

    def variant(self, language):
        lyrics = self.lyrics[language]
        lines = []
        for index, row in enumerate(self.ns["parsed_timed_lyrics"](lyrics)):
            base = (1.2, 4.3, 8.0)[index]
            duration = (1.4, 1.2, 0.4)[index]
            line = {"index": index, "text": row["text"], "time": row["time"],
                    "analysisTime": base, "duration": duration, "wordSpans": [], "wordTimes": []}
            if row["rest"]:
                line["rest"] = True
            else:
                line["alignment"] = {"start": base, "end": base + duration,
                                     "source": "fixture-bound-acoustic", "quality": "acoustic_aligned"}
                if language != "zh":
                    words = self.ns["lyrics_word_tokens"](row["text"])
                    line["wordSpans"] = [{"word": words[0], "start": 0.0, "end": 0.5,
                                          "fillEnd": 0.45},
                                         {"word": words[1], "start": 0.7, "end": duration,
                                          "fillEnd": duration}]
            lines.append(line)
        return {"meta": self.ns["music_analysis_cache_meta"](self.audio, lyrics),
                "lyricsSha256": self.ns["file_sha256"](lyrics),
                "analysis": {"ok": True, "path": "example.mp3", "lyricsPath": lyrics.name,
                             "duration": 10.0, "method": "fixture-acoustic", "lines": lines}}

    def write_sidecar(self):
        self.sidecar.write_text(json.dumps(self.body, ensure_ascii=False), encoding="utf-8")

    def load(self, language=""):
        return self.ns["read_music_alignment_sidecar"](self.audio, self.lyrics[language])

    def test_valid_sidecar_has_priority_and_current_marks(self):
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics[""], {"ok": True, "method": "legacy"})
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["method"], "fixture-acoustic")
        self.assertEqual(result["manualMarks"], self.marks)
        self.assertEqual(self.decode_calls, 0)
        self.assertEqual(result["lines"][0]["alignment"]["start"], 1.2)

    def test_language_switches_return_bound_variant_without_rewrite(self):
        before = self.sidecar.read_bytes()
        for language in ("en", "zh", "", "en"):
            result = self.ns["music_lyrics_analysis"]("example.mp3", language)
            self.assertEqual(result["lyricsPath"], self.lyrics[language].name)
            self.assertEqual(result["lyricsLanguage"], language)
            self.assertEqual(result["lines"][0]["text"], "你好 世界" if language == "zh" else "Hello, world")
            if language == "zh":
                self.assertEqual(result["lines"][0]["wordSpans"], [])
        self.assertEqual(self.sidecar.read_bytes(), before)
        self.assertEqual(self.decode_calls, 0)

    def test_mark_invalidation_removes_only_v88_cache(self):
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics[""], {"ok": True, "method": "legacy"})
        ordinary = self.ns["music_analysis_cache_path"](self.audio)
        before = self.sidecar.read_bytes()
        self.ns["invalidate_music_analysis_cache"](self.audio)
        self.assertFalse(ordinary.exists())
        self.marks[0]["time"] = 1.3
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["manualMarks"][0]["time"], 1.3)
        self.assertEqual(result["lines"][0]["alignment"]["start"], 1.2)
        self.assertEqual(self.sidecar.read_bytes(), before)

    def test_return_is_deep_copy(self):
        with patch.object(json, "loads", return_value=self.body):
            result = self.load()
        result["lines"][0]["wordSpans"][0]["start"] = 999
        self.assertEqual(self.body["variants"][0]["analysis"]["lines"][0]["wordSpans"][0]["start"], 0.0)

    def test_casefold_words_return_source_tokens_without_payload_mutation(self):
        source_line = self.body["variants"][0]["analysis"]["lines"][0]
        source_words = self.ns["lyrics_word_tokens"](source_line["text"])
        source_line["wordSpans"][0]["word"] = source_words[0].lower()
        source_line["wordSpans"][1]["word"] = source_words[1].upper()
        original_payload = copy.deepcopy(self.body)
        with patch.object(json, "loads", return_value=self.body):
            result = self.load()
        self.assertIsNotNone(result)
        self.assertEqual([span["word"] for span in result["lines"][0]["wordSpans"]], source_words)
        self.assertEqual(self.body, original_payload)
        result["lines"][0]["wordSpans"][0]["word"] = "mutated returned copy"
        self.assertEqual(self.body, original_payload)

    def test_malformed_sidecar_falls_back_to_ordinary_cache(self):
        self.sidecar.write_text("{", encoding="utf-8")
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics[""], {"ok": True, "method": "legacy", "lines": []})
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["method"], "legacy")
        self.assertEqual(self.decode_calls, 0)
        self.assertEqual(self.sidecar.read_text(encoding="utf-8"), "{")

    def test_unrelated_audio_uses_ordinary_cache(self):
        self.sidecar.unlink()
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics[""], {"ok": True, "method": "legacy", "lines": []})
        self.assertEqual(self.ns["music_lyrics_analysis"]("example.mp3")["method"], "legacy")
        self.assertFalse(self.sidecar.exists())

    def test_audio_hash_detects_change_even_with_same_size_and_mtime(self):
        before = self.audio.stat()
        content = self.audio.read_bytes()
        self.audio.write_bytes(b"X" + content[1:])
        os.utime(self.audio, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.ns["music_analysis_cache_meta"](self.audio, self.lyrics[""]), self.body["variants"][0]["meta"])
        self.assertIsNone(self.load())

    def test_lyrics_hash_detects_change_even_with_same_size_and_mtime(self):
        lyrics = self.lyrics[""]
        before = lyrics.stat()
        lyrics.write_bytes(lyrics.read_bytes().replace(b"Hello", b"Jello"))
        os.utime(lyrics, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertIsNone(self.load())

    def test_metadata_format_and_ambiguous_variants_are_rejected(self):
        original = copy.deepcopy(self.body)
        edits = [lambda b: b.update(format=True), lambda b: b.update(format=2),
                 lambda b: b.update(audioSha256=""), lambda b: b.update(variants={}),
                 lambda b: b["variants"][0]["meta"].update(version=89),
                 lambda b: b["variants"].append(copy.deepcopy(b["variants"][0]))]
        for edit in edits:
            with self.subTest(edit=edits.index(edit)):
                self.body = copy.deepcopy(original)
                edit(self.body)
                self.write_sidecar()
                self.assertIsNone(self.load())

    def test_row_and_interval_mismatches_are_rejected(self):
        original = copy.deepcopy(self.body)
        edits = [lambda a: a.update(path="another.mp3"), lambda a: a.update(lyricsPath="another.lrc"),
                 lambda a: a.update(duration=math.nan), lambda a: a["lines"].pop(),
                 lambda a: a["lines"][0].update(index=True), lambda a: a["lines"][0].update(text="Wrong"),
                 lambda a: a["lines"][0].update(rest=True), lambda a: a["lines"][0].update(time=2),
                 lambda a: a["lines"][0].update(analysisTime=math.inf),
                 lambda a: a["lines"][0]["alignment"].update(start=-1),
                 lambda a: a["lines"][0]["alignment"].update(end=11),
                 lambda a: a["lines"][0]["alignment"].update(source=""),
                 lambda a: a["lines"][0]["alignment"].update(quality=""),
                 lambda a: a["lines"][0]["wordSpans"].pop(),
                 lambda a: a["lines"][0]["wordSpans"][0].update(word="Wrong"),
                 lambda a: a["lines"][0]["wordSpans"][0].update(start=math.nan),
                 lambda a: a["lines"][0]["wordSpans"][0].update(fillEnd=5),
                 lambda a: a["lines"][0]["wordSpans"][1].update(start=0.1),
                 lambda a: a["lines"][0]["wordSpans"][1].update(end=5),
                 lambda a: a["lines"][2].update(wordSpans=[{"word": "Wrong"}])]
        for edit in edits:
            with self.subTest(edit=edits.index(edit)):
                self.body = copy.deepcopy(original)
                edit(self.body["variants"][0]["analysis"])
                self.write_sidecar()
                self.assertIsNone(self.load())

    def test_unbound_acoustic_ordinary_cache_cannot_bypass_rejection(self):
        self.body["format"] = 2
        self.write_sidecar()
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics[""], self.body["variants"][0]["analysis"])
        self.ns["parsed_timed_lyrics"] = lambda _path: [{"time": 1.0, "text": "", "rest": True}]
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["method"], "rms-edge-speechflow-first-word-pulse-fill-v88")
        self.assertEqual(self.decode_calls, 1)  # Stub only; no audio decoder runs.
        self.assertNotIn("alignment", result["lines"][0])
        self.assertEqual(json.loads(self.sidecar.read_text(encoding="utf-8"))["format"], 2)


if __name__ == "__main__":
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AlignmentSidecarTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = {"passed": result.wasSuccessful(), "testsRun": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "candidateSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "testSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "audioDecodeExecuted": False, "appImportExecuted": False,
              "formalCacheOrProductionModified": False, "details": stream.getvalue()}
    print(json.dumps({k: v for k, v in record.items() if k != "details"}, ensure_ascii=True))
    if not result.wasSuccessful():
        print(json.dumps({"details": stream.getvalue()}, ensure_ascii=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
