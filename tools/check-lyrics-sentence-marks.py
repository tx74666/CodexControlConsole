"""Sentence mark persistence tests use extracted functions and synthetic files only."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "world_console.py"
FUNCTIONS = {
    "atomic_write_json", "music_relative_path", "normalize_lyrics_language",
    "read_music_lyric_marks", "write_music_lyric_marks", "music_lyric_marks_for_path",
    "music_lyric_mark_sort_key", "normalize_music_lyric_mark_role", "build_music_lyric_mark",
    "same_music_lyric_mark_slot", "music_lyric_mark_expected_time",
    "apply_music_lyric_mark_operations", "invalidate_music_analysis_cache",
    "save_music_lyric_mark", "save_music_lyric_marks_batch", "ensure_music_analysis_dir",
    "music_analysis_cache_path", "music_analysis_cache_meta", "read_music_analysis_cache",
    "write_music_analysis_cache", "has_acoustic_alignment", "attach_music_sentence_marks",
    "music_lyrics_analysis",
}


class SentenceMarkTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sentence-mark-fixture-", dir=ROOT))
        self.music = self.root / "music"
        self.music.mkdir()
        self.audio = self.music / "example.mp3"
        self.audio.write_bytes(b"synthetic audio, never decoded")
        self.other = self.music / "other.mp3"
        self.other.write_bytes(b"other synthetic audio")
        self.lyrics = self.music / "example.lrc"
        self.lyrics.write_text("[00:01]First sentence\n[00:04]Second sentence\n", encoding="utf-8")
        self.store = self.root / "cache/music_lyric_marks.json"
        self.legacy = {"kind": "boundary", "lineIndex": 0, "boundaryIndex": 0,
                       "role": "start", "time": 1.2, "word": "First", "unknownLegacy": [1, 2]}
        self.initial = {"format": "keep", "unknownTop": {"x": 3}, "tracks": {
            "example.mp3": [self.legacy, {"kind": "future", "lineIndex": "keep", "custom": 7}],
            "other.mp3": [{"kind": "future", "custom": ["untouched"]}],
        }}
        self.analysis = {"ok": True, "path": "example.mp3", "lyricsPath": "example.lrc",
                         "duration": 10, "method": "existing-analysis", "unknownAnalysis": [7], "lines": [
            {"index": 0, "text": "First sentence", "time": 1, "analysisTime": 1.1, "duration": 2,
             "wordTimes": [0, 1, 2], "wordSpans": [{"word": "First", "start": 0, "end": 1}],
             "waveform": [{"time": 1, "energy": .5}], "alignment": {"source": "original"}},
            {"index": 1, "text": "Second sentence", "time": 4, "duration": 2,
             "wordTimes": [.1, 1], "wordSpans": [{"word": "Second", "start": .1, "end": 1}]},
        ]}

        def path_from_relative(relative):
            candidate = (self.music / relative).resolve()
            if not candidate.is_relative_to(self.music.resolve()) or not candidate.is_file():
                raise ValueError("invalid synthetic audio path")
            return candidate

        def forbidden_decode(_path):
            raise AssertionError("sentence marking must not decode audio")

        self.ns = {"Path": Path, "copy": copy, "datetime": datetime, "timezone": timezone,
                   "hashlib": hashlib, "json": json, "math": math, "os": os, "tempfile": tempfile,
                   "MUSIC_DIR": self.music, "MUSIC_ANALYSIS_DIR": self.root / "cache/music_analysis",
                   "MUSIC_LYRIC_MARKS_FILE": self.store, "MUSIC_LYRIC_MARKS_LOCK": threading.RLock(),
                   "LYRICS_LANGUAGE_ORDER": ("en", "zh", "fr"),
                   "music_path_from_relative": path_from_relative,
                   "lyrics_path_from_music_path": lambda path, language="": self.lyrics,
                   "read_music_alignment_sidecar": lambda *args: None,
                   "decoded_music_flux": forbidden_decode}
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
        self.assertEqual({node.name for node in nodes}, FUNCTIONS)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), self.ns)
        self.ns["write_music_lyric_marks"](copy.deepcopy(self.initial))
        self.ns["write_music_analysis_cache"](self.audio, self.lyrics, self.analysis)
        self.cache = self.ns["music_analysis_cache_path"](self.audio)
        self.cache_before = self.cache.read_bytes()

    def tearDown(self):
        assert self.root.resolve().is_relative_to(ROOT.resolve())
        shutil.rmtree(self.root)

    def point(self, line=0, role="start", time=1.25, **extra):
        return {"path": "example.mp3", "kind": "sentence", "lineIndex": line, "role": role,
                "time": time, "lineText": "First sentence" if line == 0 else "Second sentence",
                "note": "manual sentence", **extra}

    def stored(self):
        return self.ns["read_music_lyric_marks"](strict=True)

    def save(self, **extra):
        return self.ns["save_music_lyric_mark"](self.point(**extra))

    def batch(self, items):
        return self.ns["save_music_lyric_marks_batch"]({"marks": items})

    def sentence(self, language=""):
        return [mark for mark in self.ns["music_lyric_marks_for_path"](self.audio)
                if mark["kind"] == "sentence" and mark.get("lyricsLanguage", "") == language]

    def test_mixed_legacy_sentence_and_unknown_records_preserved(self):
        result = self.save(expectedTime=None)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["marks"]), 2)
        stored = self.stored()
        self.assertEqual(stored["unknownTop"], self.initial["unknownTop"])
        self.assertEqual(stored["tracks"]["other.mp3"], self.initial["tracks"]["other.mp3"])
        self.assertIn(self.legacy, stored["tracks"]["example.mp3"])
        self.assertIn(self.initial["tracks"]["example.mp3"][1], stored["tracks"]["example.mp3"])
        self.assertEqual(self.cache.read_bytes(), self.cache_before)

    def test_transition_pair_has_exact_same_clock_and_no_word_dependency(self):
        self.batch([self.point(role="end", time=3.125, expectedTime=None),
                    self.point(line=1, time=3.125, expectedTime=None)])
        self.assertEqual([(p["lineIndex"], p["role"], p["time"]) for p in self.sentence()],
                         [(0, "end", 3.125), (1, "start", 3.125)])
        self.assertTrue(all("boundaryIndex" not in mark for mark in self.sentence()))
        self.assertEqual(self.cache.read_bytes(), self.cache_before)

    def test_every_invalid_pair_is_rejected_before_any_write(self):
        invalid = [{"time": math.nan}, {"time": math.inf}, {"time": -1}, {"time": True},
                   {"time": "2"}, {"lineIndex": 1.2}, {"lineIndex": "1"}, {"lineIndex": True},
                   {"lineIndex": -1}, {"role": "word"}, {"role": []}, {"kind": []},
                   {"lyricsLanguage": "unknown"}, {"expectedTime": math.nan}, {"action": "clear"}]
        for fields in invalid:
            with self.subTest(fields=fields):
                before = self.store.read_bytes()
                with self.assertRaises(ValueError):
                    self.batch([self.point(role="end", time=3), self.point(line=1, **fields)])
                self.assertEqual(self.store.read_bytes(), before)
                self.assertEqual(self.cache.read_bytes(), self.cache_before)
        with self.assertRaises(ValueError):
            self.batch([self.point(), None])

    def test_overwrite_and_removal_are_narrow_and_keep_custom_fields(self):
        self.save()
        body = self.stored()
        sentence = next(p for p in body["tracks"]["example.mp3"] if p.get("kind") == "sentence")
        sentence["futureField"] = {"preserve": True}
        self.ns["write_music_lyric_marks"](body)
        self.save(time=1.5, expectedTime=1.25)
        self.assertEqual(self.sentence()[0]["futureField"], {"preserve": True})
        result = self.ns["save_music_lyric_mark"]({"path": "example.mp3", "kind": "sentence",
            "lineIndex": 0, "role": "start", "action": "remove", "expectedTime": 1.5})
        self.assertTrue(result["removed"])
        self.assertEqual(self.sentence(), [])
        self.assertIn(self.legacy, self.stored()["tracks"]["example.mp3"])
        self.assertEqual(self.stored()["tracks"]["other.mp3"], self.initial["tracks"]["other.mp3"])
        with self.assertRaises(ValueError):
            self.ns["save_music_lyric_mark"]({"path": "example.mp3", **self.legacy, "action": "remove"})

    def test_cas_pair_rejects_concurrent_changed_point_atomically(self):
        self.save(role="end", time=3)
        before = self.store.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.batch([self.point(role="end", time=3.5, expectedTime=2.5),
                        self.point(line=1, time=3.5, expectedTime=None)])
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(len(self.sentence()), 1)

    def test_lost_response_retry_is_idempotent_and_keeps_created_identity(self):
        points = [self.point(role="end", time=3, expectedTime=None),
                  self.point(line=1, time=3, expectedTime=None)]
        self.batch(points)
        first = copy.deepcopy(self.sentence())
        self.batch(points)
        self.assertEqual(self.sentence(), first)
        removals = [{**p, "action": "remove", "expectedTime": 3} for p in points]
        self.batch(removals)
        self.batch(removals)
        self.assertEqual(self.sentence(), [])

    def test_coalesced_duplicate_slots_last_value_and_concurrent_distinct_slots(self):
        self.batch([self.point(time=1.2), self.point(time=1.4)])
        self.assertEqual(len(self.sentence()), 1)
        self.assertEqual(self.sentence()[0]["time"], 1.4)
        barrier = threading.Barrier(8)
        errors = []
        def worker(index):
            try:
                barrier.wait(timeout=5)
                self.save(line=index + 2, time=index + 4, expectedTime=None)
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(self.sentence()), 9)
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_language_scopes_and_changed_caption_do_not_remap_word_data(self):
        self.save(time=1.3)
        self.save(time=1.8, lyricsLanguage="zh", lineText="翻译句子")
        self.assertEqual(len(self.sentence()), 1)
        self.assertEqual(len(self.sentence("zh")), 1)
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["lyricsLanguage"], "")
        self.assertEqual(result["lines"][0]["sentenceStart"], 1.3)
        self.assertNotIn("sentenceEnd", result["lines"][0])
        original = copy.deepcopy(result)
        for line in original["lines"]:
            for key in ("sentenceStart", "sentenceEnd", "sentenceMarks"):
                line.pop(key, None)
        self.assertEqual(original["lines"], self.analysis["lines"])
        altered = copy.deepcopy(self.analysis)
        altered["lines"][0]["text"] = "A different source sentence"
        overlay = self.ns["attach_music_sentence_marks"](altered, self.sentence())
        self.assertNotIn("sentenceStart", overlay["lines"][0])
        self.assertEqual(altered["lines"][0]["text"], "A different source sentence")
        self.assertEqual(self.cache.read_bytes(), self.cache_before)

    def test_acoustic_payload_return_is_deep_copy_and_never_rewritten(self):
        source = copy.deepcopy(self.analysis)
        source["method"] = "acoustic"
        source["lines"][0]["alignment"]["quality"] = "acoustic_aligned"
        self.save(role="end", time=2.75)
        self.ns["read_music_alignment_sidecar"] = lambda *args: source
        before = copy.deepcopy(source)
        result = self.ns["music_lyrics_analysis"]("example.mp3")
        self.assertEqual(result["lines"][0]["sentenceEnd"], 2.75)
        result["lines"][0]["wordSpans"][0]["start"] = 900
        self.assertEqual(source, before)
        self.assertEqual(self.cache.read_bytes(), self.cache_before)

    def test_long_sentence_identity_is_exact_and_never_silently_truncated(self):
        text = "A long sentence, " * 80
        self.save(lineText=text)
        self.assertEqual(self.sentence()[0]["lineText"], text)
        source = copy.deepcopy(self.analysis)
        source["lines"][0]["text"] = text
        overlaid = self.ns["attach_music_sentence_marks"](source, self.sentence())
        self.assertEqual(overlaid["lines"][0]["sentenceStart"], 1.25)
        before = self.store.read_bytes()
        for invalid in ("x" * 16385, ["invalid"]):
            with self.assertRaises(ValueError):
                self.save(lineText=invalid)
            self.assertEqual(self.store.read_bytes(), before)

    def test_failed_write_and_corrupt_store_are_not_reported_success(self):
        before = self.store.read_bytes()
        with patch.dict(self.ns, {"atomic_write_json": lambda *args: (_ for _ in ()).throw(PermissionError())}):
            with self.assertRaises(PermissionError):
                self.save()
        self.assertEqual(self.store.read_bytes(), before)
        self.store.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "preserved"):
            self.save()
        self.assertEqual(self.store.read_bytes(), b"{broken")
        self.assertEqual(self.cache.read_bytes(), self.cache_before)

    def test_legacy_boundary_save_retains_original_cache_invalidation_behavior(self):
        self.ns["save_music_lyric_mark"]({"path": "example.mp3", **self.legacy, "time": 1.4})
        self.assertFalse(self.cache.exists())
        self.assertEqual(self.stored()["tracks"]["other.mp3"], self.initial["tracks"]["other.mp3"])


if __name__ == "__main__":
    unittest.main()
