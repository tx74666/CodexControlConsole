"""Fake-only checks: no native window enumeration, focus, close, or launch."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import console_window_launcher as launcher


URL = "http://127.0.0.1:8898/workspace.html?consoleView=document"



def window(handle=101, pid=501, **changes):
    return launcher.Window(handle, pid, changes.get("title", "Codex Console - Console"),
                           changes.get("class_name", "Chrome_WidgetWin_1"),
                           changes.get("image", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"))


class FakeWindows:
    def __init__(self, windows=()):
        self.windows = {item.handle: item for item in windows}
        self.tags = {}
        self.activated = []
        self.closed = []
        self.activation_succeeds = True
        self.close_succeeds = True
        self.refuses_close = False
        self.minimized = set()
        self.background = set()

    def inspect(self, handle, scope):
        item = self.windows.get(handle)
        if item is None or not launcher._browser_window(item):
            return None
        tags = self.tags.get(handle, {})
        item = replace(item, owned=bool(tags), scope_pid=tags.get(scope, 0))
        return item if item.owned or item.scope_pid or launcher._console_window(item) else None

    def scan(self, scope):
        return set(self.windows), [item for handle in self.windows if (item := self.inspect(handle, scope))]

    def tag(self, item, scope):
        self.tags.setdefault(item.handle, {})[scope] = item.pid
        return True

    def activate(self, item):
        self.activated.append(item.handle)
        return self.activation_succeeds

    def close(self, item, scope):
        current = self.inspect(item.handle, scope)
        if not launcher._same_window(current, item) or not launcher._belongs(current):
            return False
        self.closed.append(item.handle)
        if not self.close_succeeds:
            return False
        if not self.refuses_close:
            del self.windows[item.handle]
            self.tags.pop(item.handle, None)
        return True

    def alive(self, item):
        current = self.windows.get(item.handle)
        return bool(current and current.pid == item.pid)


class LauncherChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='console-window-launcher-check-')
        self.data = self.temporary.name
        self.fake = FakeWindows()
        self.now = 0
        self.scope = launcher._scope_property(URL, self.data)
        self.patches = [
            patch.object(launcher, "_native_windows", side_effect=lambda: self.fake),
            patch.object(launcher.time, "monotonic", side_effect=lambda: self.now),
            patch.object(launcher.time, "time", side_effect=lambda: 1000 + self.now),
            patch.object(launcher.time, "sleep", side_effect=self.sleep),
            # Any accidental native discovery/activation call fails this test.
            patch.object(launcher, "_windows_apis", side_effect=AssertionError("native APIs forbidden in check")),
            patch.object(launcher, "_activate_window", side_effect=AssertionError("native focus forbidden in check")),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def sleep(self, seconds):
        self.now += seconds

    def own(self, item=None, scope=None):
        item = item or window()
        self.fake.windows[item.handle] = item
        self.fake.tag(item, scope or self.scope)
        return item

    def test_strict_title_process_and_class_matching(self):
        for title in ("Codex Console", "Codex Console - Console", "Codex Console - 音乐", "Codex Console - Wallpaper"):
            self.assertTrue(launcher._console_window(window(title=title)))
        for title in ("Downloads", "Codex Console - Downloads", "Codex Console - Console - Microsoft Edge",
                      "Codex Console - Google Chrome", "Codex Console - Music - album", "Other Codex Console",
                      "Codex Console - Unknown", "Codex Console "):
            self.assertFalse(launcher._console_window(window(title=title)), title)
        self.assertFalse(launcher._console_window(window(image="notepad.exe")))
        self.assertFalse(launcher._console_window(window(class_name="OtherClass")))

    def test_scope_separates_directory_and_port(self):
        self.assertNotEqual(self.scope, launcher._scope_property(URL.replace("8898", "8899"), self.data))
        self.assertNotEqual(self.scope, launcher._scope_property(URL, self.data + "-other"))
        self.assertEqual(self.scope, launcher._scope_property(URL.replace("127.0.0.1", "localhost"), self.data))
        with self.assertRaises(ValueError):
            launcher._scope_property("https://example.com/", self.data)

    def test_new_window_tagged_then_reused_even_if_foreground_denied(self):
        starter = Mock(side_effect=lambda url: self.fake.windows.update({101: window()}))
        first = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(first["launched"])
        self.assertEqual(self.fake.tags[101][self.scope], 501)
        self.fake.activation_succeeds = False
        second = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(second["existing"])
        self.assertFalse(second["activated"])
        self.assertFalse(second["launched"])
        self.assertEqual(starter.call_count, 1)

    def test_background_and_minimized_owned_windows_reused(self):
        self.own()
        self.fake.background.add(101)
        self.fake.minimized.add(101)
        starter = Mock()
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(result["existing"] and result["activated"])
        starter.assert_not_called()

    def test_owned_blank_or_error_title_blocks_duplicate_and_replacement(self):
        for title in ("", "This site can't be reached", "Codex Console - Console - Microsoft Edge"):
            self.fake = FakeWindows()
            self.own(window(title=title))
            starter = Mock()
            repeated = launcher.launch_or_focus(URL, starter, self.data)
            self.assertTrue(repeated["existing"])
            replacement = launcher.launch_or_focus(URL, starter, self.data, replace=True)
            self.assertEqual(replacement["status"], "owned-title-unconfirmed")
            self.assertTrue(replacement["blocked"])
            self.assertFalse(self.fake.closed)
            starter.assert_not_called()

    def test_native_inspect_retains_ownership_when_title_changes(self):
        native = object.__new__(launcher._NativeWindows)
        user32 = native.user32 = Mock()
        user32.IsWindow.return_value = True
        def class_name(handle, buffer, size):
            buffer.value = "Chrome_WidgetWin_1"
            return len(buffer.value)
        def process_id(handle, pointer):
            pointer._obj.value = 501
            return 1
        user32.GetClassNameW.side_effect = class_name
        user32.GetWindowThreadProcessId.side_effect = process_id
        with patch.object(launcher, "_process_image_path", return_value=window().image):
            for title in ("", "Navigation error"):
                user32.GetWindowTextLengthW.return_value = len(title)
                def read_title(handle, buffer, size):
                    buffer.value = title
                    return len(title)
                user32.GetWindowTextW.side_effect = read_title
                user32.GetPropW.side_effect = lambda handle, key: 1 if key == launcher._OWNER_PROPERTY else 501
                own = native.inspect(101, self.scope)
                self.assertIsNotNone(own)
                self.assertTrue(launcher._belongs(own))
                self.assertEqual(own.title, title)
                user32.GetPropW.side_effect = lambda handle, key: 1 if key == launcher._OWNER_PROPERTY else 0
                foreign = native.inspect(101, self.scope)
                self.assertTrue(foreign.owned)
                self.assertEqual(foreign.scope_pid, 0)
                user32.GetPropW.side_effect = None
                user32.GetPropW.return_value = 0
                self.assertIsNone(native.inspect(101, self.scope))

    def test_legacy_focus_never_confers_ownership_or_close_authority(self):
        self.fake.windows[101] = window()
        starter = Mock()
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(result["activated"])
        self.assertFalse(self.fake.tags)
        replacement = launcher.launch_or_focus(URL, starter, self.data, replace=True)
        self.assertTrue(replacement["legacyNeedsRefresh"] and replacement["blocked"])
        self.assertFalse(self.fake.closed)
        starter.assert_not_called()

    def test_multiple_legacy_windows_are_ambiguous(self):
        self.fake.windows = {101: window(), 102: window(102, 502)}
        starter = Mock()
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertEqual(result["status"], "ambiguous-legacy")
        self.assertFalse(self.fake.activated)
        starter.assert_not_called()

    def test_other_scope_is_not_focused_tagged_or_closed(self):
        foreign = launcher._scope_property(URL, self.data + "-foreign")
        self.own(scope=foreign)
        starter = Mock(side_effect=lambda url: self.fake.windows.update({202: window(202, 502)}))
        result = launcher.launch_or_focus(URL, starter, self.data, replace=True)
        self.assertTrue(result["launched"])
        self.assertFalse(self.fake.closed)
        self.assertEqual(self.fake.tags[101], {foreign: 501})
        self.assertEqual(self.fake.activated, [202])

    def test_normal_replacement_waits_for_owned_close(self):
        self.own()
        def start(url):
            self.assertNotIn(101, self.fake.windows)
            self.fake.windows[202] = window(202, 502)
        starter = Mock(side_effect=start)
        result = launcher.launch_or_focus(URL, starter, self.data, replace=True)
        self.assertTrue(result["launched"] and result["replaced"])
        self.assertEqual(self.fake.closed, [101])
        starter.assert_called_once_with(URL)

    def test_close_cancel_or_post_failure_never_opens_replacement(self):
        for refused in (False, True):
            self.fake = FakeWindows()
            self.own()
            self.fake.close_succeeds = refused
            self.fake.refuses_close = refused
            starter = Mock()
            result = launcher.launch_or_focus(URL, starter, self.data, replace=True)
            self.assertTrue(result["blocked"])
            self.assertFalse(result["launched"])
            self.assertEqual(result["status"], "close-pending" if refused else "close-rejected")
            starter.assert_not_called()

    def test_changed_pid_in_scope_tag_blocks_reuse_and_close(self):
        self.own()
        self.fake.windows[101] = window(pid=999)
        starter = Mock()
        result = launcher.launch_or_focus(URL, starter, self.data, replace=True)
        self.assertEqual(result["status"], "identity-mismatch")
        self.assertFalse(self.fake.closed)
        starter.assert_not_called()

    def test_ambiguous_new_windows_not_tagged_or_launched_again(self):
        starter = Mock(side_effect=lambda url: self.fake.windows.update({101: window(), 102: window(102, 502)}))
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertEqual(result["status"], "launched-ambiguous")
        self.assertFalse(self.fake.tags)
        self.assertEqual(starter.call_count, 1)

    def test_pending_window_does_not_retry_starter(self):
        starter = Mock()
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(result["launched"] and result["pending"])
        marker = launcher._PendingStart(self.data, self.scope)
        self.assertTrue(marker.path.is_file())
        # Each call reconstructs its pending reader from disk, as a second
        # serialized process would. Slow cold start must not call starter twice.
        second = launcher.launch_or_focus(URL, starter, self.data)
        self.assertFalse(second["launched"])
        self.assertTrue(second["pending"])
        self.assertEqual(starter.call_count, 1)
        self.fake.windows[101] = window()
        observed = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(observed["existing"])
        self.assertFalse(marker.path.exists())
        self.assertFalse(self.fake.tags)  # A late legacy match is focus-only.

    def test_pending_expires_before_a_new_attempt_is_allowed(self):
        starter = Mock()
        launcher.launch_or_focus(URL, starter, self.data)
        self.now += launcher._PENDING_SECONDS + 1
        retried = launcher.launch_or_focus(URL, starter, self.data)
        self.assertTrue(retried["launched"])
        self.assertEqual(starter.call_count, 2)

    def test_starter_failure_clears_pending_marker(self):
        starter = Mock(side_effect=OSError("browser unavailable"))
        result = launcher.launch_or_focus(URL, starter, self.data)
        self.assertEqual(result["status"], "launch-failed")
        self.assertFalse(launcher._PendingStart(self.data, self.scope).path.exists())

    def test_scan_failure_blocks_launch(self):
        self.fake.scan = Mock(side_effect=OSError("not available"))
        starter = Mock()
        self.assertEqual(launcher.launch_or_focus(URL, starter, self.data)["status"], "scan-failed")
        starter.assert_not_called()

    def test_native_close_method_only_posts_wm_close_after_revalidation(self):
        native = object.__new__(launcher._NativeWindows)
        native.user32 = Mock()
        original = replace(window(), owned=True, scope_pid=501)
        native.inspect = Mock(return_value=original)
        self.assertTrue(native.close(original, self.scope))
        native.user32.PostMessageW.assert_called_once_with(101, 0x0010, 0, 0)
        native.user32.PostMessageW.reset_mock()
        native.inspect.return_value = replace(original, pid=999)
        self.assertFalse(native.close(original, self.scope))
        native.inspect.return_value = replace(original, owned=False, scope_pid=0)
        self.assertFalse(native.close(original, self.scope))
        native.user32.PostMessageW.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
