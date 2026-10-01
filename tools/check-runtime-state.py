import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import world_console  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_together(functions):
    barrier = threading.Barrier(len(functions))
    errors = []

    def invoke(function):
        try:
            barrier.wait(timeout=5)
            function()
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=invoke, args=(function,)) for function in functions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    require(not any(thread.is_alive() for thread in threads), "concurrent state test did not finish")
    if errors:
        raise errors[0]


def wait_until(predicate, message, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def check_atomic_json_files(root):
    created = []
    original_mkstemp = tempfile.mkstemp

    def tracked_mkstemp(*args, **kwargs):
        descriptor, name = original_mkstemp(*args, **kwargs)
        created.append(Path(name))
        return descriptor, name

    with mock.patch.object(world_console.tempfile, "mkstemp", tracked_mkstemp):
        run_together([
            lambda index=index: world_console.atomic_write_json(
                root / f"atomic-{index}.json",
                {"index": index},
            )
            for index in range(12)
        ])

    require(len(created) == 12, "atomic JSON writes did not use a temporary file")
    require(len({str(path) for path in created}) == len(created), "atomic JSON temporary names collided")
    require(not any(path.exists() for path in created), "successful atomic JSON writes left temporary files")

    target = root / "replace-failure.json"
    target.write_text('{"preserved": true}\n', encoding="utf-8")
    before = target.read_bytes()
    failed_temporary = []

    def tracked_failure_mkstemp(*args, **kwargs):
        descriptor, name = original_mkstemp(*args, **kwargs)
        failed_temporary.append(Path(name))
        return descriptor, name

    with (
        mock.patch.object(world_console.tempfile, "mkstemp", tracked_failure_mkstemp),
        mock.patch.object(world_console.os, "replace", side_effect=OSError("replace failed")),
    ):
        try:
            world_console.atomic_write_json(target, {"preserved": False})
        except OSError:
            pass
        else:
            raise AssertionError("atomic JSON write hid an os.replace failure")

    require(target.read_bytes() == before, "failed atomic JSON write damaged the formal file")
    require(not any(path.exists() for path in failed_temporary), "failed atomic JSON write left a temporary file")


def check_concurrent_state_updates(root):
    console_file = root / "console-state.json"
    music_file = root / "music-state.json"
    music_backup = root / "music-state.previous.json"
    lyric_file = root / "music-lyric-marks.json"
    music_dir = root / "music"
    music_dir.mkdir()
    (music_dir / "one.mp3").write_bytes(b"one")
    (music_dir / "two.mp3").write_bytes(b"two")

    with mock.patch.object(world_console, "CONSOLE_STATE_FILE", console_file):
        world_console.write_console_state({})
        run_together([
            lambda: world_console.write_console_state({"lastModule": "music"}),
            lambda: world_console.write_console_state({"archive": ["workspace"]}),
        ])
        console_state = world_console.read_console_state()
        require(console_state["lastModule"] == "music", "concurrent console lastModule update was lost")
        require(console_state["archive"] == ["workspace"], "concurrent console archive update was lost")

    with (
        mock.patch.object(world_console, "MUSIC_STATE_FILE", music_file),
        mock.patch.object(world_console, "MUSIC_STATE_BACKUP_FILE", music_backup),
        mock.patch.object(world_console, "read_release_defaults", return_value={"music": {}}),
        mock.patch.object(
            world_console,
            "localize_release_music_state",
            side_effect=lambda raw: world_console.normalize_music_state(raw),
        ),
    ):
        world_console.store_music_state(world_console.normalize_music_state({}))
        run_together([
            lambda: world_console.write_music_state({"selectedTrackPath": "one.mp3"}),
            lambda: world_console.write_music_state({"promotedLibraryTracks": {"two.mp3": "two.mp3"}}),
        ])
        music_state = world_console.read_music_state()
        require(music_state.get("selectedTrackPath") == "one.mp3", "concurrent selected-track update was lost")
        require(
            music_state.get("promotedLibraryTracks") == {"two.mp3": "two.mp3"},
            "concurrent promoted-track update was lost",
        )
        require(music_backup.exists(), "music state backup was not written atomically")

    mark_base = {
        "time": 1.25,
        "lineIndex": 0,
        "boundaryIndex": 0,
        "role": "start",
        "word": "word",
    }
    with (
        mock.patch.object(world_console, "MUSIC_DIR", music_dir),
        mock.patch.object(world_console, "MUSIC_ANALYSIS_DIR", root / "analysis"),
        mock.patch.object(world_console, "MUSIC_LYRIC_MARKS_FILE", lyric_file),
    ):
        run_together([
            lambda: world_console.save_music_lyric_mark({**mark_base, "path": "one.mp3"}),
            lambda: world_console.save_music_lyric_marks_batch({
                "marks": [{**mark_base, "path": "two.mp3", "boundaryIndex": 1}],
            }),
        ])
        marks = world_console.read_music_lyric_marks().get("tracks", {})
        require(len(marks.get("one.mp3", [])) == 1, "single lyric-mark transaction was lost")
        require(len(marks.get("two.mp3", [])) == 1, "batch lyric-mark transaction was lost")

    require(not list(root.rglob("*.tmp")), "runtime state operations left fixed or unique temporary files")


def check_bounded_music_scheduler():
    release = threading.Event()
    state_lock = threading.Lock()
    state = {"active": 0, "maximum": 0, "finished": 0}

    def runner(_task_id):
        with state_lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        release.wait(timeout=10)
        with state_lock:
            state["active"] -= 1
            state["finished"] += 1

    scheduler = world_console.MusicLibraryImportScheduler(runner, max_workers=2, max_pending=8)
    require(scheduler.submit(0), "first music import was not accepted")
    require(scheduler.submit(1), "second music import was not accepted")
    wait_until(lambda: state["active"] == 2, "two music import workers did not start")

    for task_id in range(2, 10):
        require(scheduler.submit(task_id), f"waiting music import {task_id} was not accepted")
    require(scheduler.pending_count == 8, "music import waiting queue is not bounded at eight")
    require(not scheduler.submit(10), "music import queue accepted a ninth waiting task")
    require(state["maximum"] == 2, "more than two music imports ran concurrently")

    release.set()
    wait_until(lambda: state["finished"] == 10, "accepted music imports did not drain")
    require(state["maximum"] == 2, "music import concurrency exceeded two while draining")


def check_music_import_limits_and_failures(root):
    entries = [{"id": str(index)} for index in range(600)]
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"title": "Large", "entries": entries}),
        stderr="",
    )
    with (
        mock.patch.object(world_console.subprocess, "run", return_value=completed) as run,
        mock.patch.object(world_console, "youtube_cookie_file", return_value=None),
        mock.patch.object(world_console, "node_js_runtime_arg", return_value=""),
    ):
        metadata = world_console.fetch_music_library_metadata(["yt-dlp"], "https://example.test/list")
    command = run.call_args.args[0]
    playlist_end = command.index("--playlist-end")
    require(command[playlist_end + 1] == "500", "yt-dlp metadata command is not capped at 500 entries")
    require(len(metadata.get("entries", [])) == 500, "metadata entries were not truncated to 500 in code")

    for failure_stage in ("metadata", "download"):
        record = {"id": failure_stage, "path": f"libraries/{failure_stage}", "name": failure_stage}
        updates = []

        def update(_library_id, **fields):
            record.update(fields)
            updates.append(dict(fields))
            return dict(record)

        metadata_mock = (
            mock.Mock(side_effect=subprocess.TimeoutExpired("yt-dlp", 180))
            if failure_stage == "metadata"
            else mock.Mock(return_value={"title": "One", "entries": [{"id": "one"}]})
        )
        download_mock = (
            mock.Mock(side_effect=subprocess.TimeoutExpired("yt-dlp", 1200))
            if failure_stage == "download"
            else mock.Mock()
        )
        with (
            mock.patch.object(world_console, "MUSIC_DIR", root / f"failure-{failure_stage}"),
            mock.patch.object(world_console, "yt_dlp_command", return_value=["yt-dlp"]),
            mock.patch.object(world_console, "update_music_library_record", side_effect=update),
            mock.patch.object(world_console, "fetch_music_library_metadata", metadata_mock),
            mock.patch.object(world_console, "download_music_library_entry", download_mock),
            mock.patch.object(world_console, "prune_duplicate_library_files", return_value=0),
            mock.patch.object(world_console, "library_tracks_for_record", return_value=[]),
        ):
            world_console.run_music_library_import(failure_stage, "https://example.test/list")

        require(record.get("status") == "failed", f"{failure_stage} exception did not finish as failed")
        require(record.get("finishedAt"), f"{failure_stage} exception did not set finishedAt")
        require(updates[-1].get("status") == "failed", f"{failure_stage} failure was not the final update")

    class FullScheduler:
        def submit(self, *_task):
            return False

    queue_music_dir = root / "queue-full-music"
    queue_library_dir = queue_music_dir / "libraries"
    queue_file = root / "queue-full-records.json"
    with (
        mock.patch.object(world_console, "MUSIC_DIR", queue_music_dir),
        mock.patch.object(world_console, "MUSIC_LIBRARY_DIR", queue_library_dir),
        mock.patch.object(world_console, "MUSIC_LIBRARY_FILE", queue_file),
        mock.patch.object(world_console, "get_music_library_import_scheduler", return_value=FullScheduler()),
    ):
        try:
            world_console.import_music_library("https://www.youtube.com/playlist?list=test", "Full")
        except ValueError as error:
            require("queue is full" in str(error).lower(), "queue-full error was not controlled")
        else:
            raise AssertionError("queue-full music import did not raise ValueError")
        records = world_console.read_music_library_records()
        require(len(records) == 1, "queue-full import did not retain one diagnostic record")
        require(records[0].get("status") == "failed", "queue-full import left a queued/grabbing record")
        require(records[0].get("finishedAt"), "queue-full import did not set finishedAt")

    class RaisingScheduler:
        def submit(self, *_task):
            raise RuntimeError("simulated worker startup failure")

    start_error_music_dir = root / "queue-start-error-music"
    start_error_library_dir = start_error_music_dir / "libraries"
    start_error_file = root / "queue-start-error-records.json"
    with (
        mock.patch.object(world_console, "MUSIC_DIR", start_error_music_dir),
        mock.patch.object(world_console, "MUSIC_LIBRARY_DIR", start_error_library_dir),
        mock.patch.object(world_console, "MUSIC_LIBRARY_FILE", start_error_file),
        mock.patch.object(world_console, "get_music_library_import_scheduler", return_value=RaisingScheduler()),
    ):
        try:
            world_console.import_music_library(
                "https://www.youtube.com/playlist?list=start-error",
                "Start error",
            )
        except ValueError as error:
            require("background worker" in str(error).lower(), "worker-start error was not controlled")
        else:
            raise AssertionError("worker-start failure did not raise ValueError")
        records = world_console.read_music_library_records()
        require(len(records) == 1, "worker-start failure did not retain one diagnostic record")
        require(records[0].get("status") == "failed", "worker-start failure left a queued record")
        require(records[0].get("finishedAt"), "worker-start failure did not set finishedAt")


def check_running_console_port_scan():
    start = 18898
    with mock.patch.object(world_console, "find_running_console",
                           return_value={"port": start + 1}) as handshake:
        require(
            world_console.running_console_port(start) == start + 1,
            "running console did not use the verified handshake's port",
        )
        handshake.assert_called_once_with(
            start, world_console.USER_DATA_DIR,
            world_console.INSTALLATION_STATE.get("installationId", ""),
        )
    with mock.patch.object(world_console, "find_running_console", return_value=None):
        require(world_console.running_console_port(start) is None,
                "a missing matching Console handshake was treated as a running instance")


def main():
    with tempfile.TemporaryDirectory(prefix="codex-runtime-state-") as temporary:
        root = Path(temporary)
        check_atomic_json_files(root)
        check_concurrent_state_updates(root)
        check_bounded_music_scheduler()
        check_music_import_limits_and_failures(root)
        check_running_console_port_scan()
    print("PASS runtime state transactions and bounded music import queue")


if __name__ == "__main__":
    main()
