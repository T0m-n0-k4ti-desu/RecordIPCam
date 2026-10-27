import contextlib
import io
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from module import ThreadManager as tm
from module import gloval_value as g


class MovieLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        g.thread_running = True
        self.cap = Mock()
        self.cap.get.return_value = 15
        self.cap.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        self.writer = Mock()
        self.writer.isOpened.return_value = True

    def tearDown(self):
        self.temp.cleanup()

    def record(self, name="cam", enabled=False):
        clock = itertools.count(0, 0.1)
        with patch.object(tm.time, "monotonic", side_effect=lambda: next(clock)), patch.object(tm.cv2, "VideoWriter", return_value=self.writer), contextlib.redirect_stdout(io.StringIO()):
            return tm.RecMovie(self.cap, str(self.root), name, 0.25, 1, save_log=enabled)

    def test_disabled_creates_no_text(self):
        self.assertTrue(self.record())
        self.assertEqual(list(self.root.rglob("*.txt")), [])

    def test_each_video_has_separate_log(self):
        self.record("one", True)
        self.record("two", True)
        logs = sorted(self.root.rglob("*.txt"))
        self.assertEqual(len(logs), 2)
        for path in logs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Result: completed", text)
            self.assertIn(str(path.with_suffix(".mp4")), text)
            self.assertIn("Frames submitted:", text)
            other = "two" if path.name.startswith("one_") else "one"
            self.assertNotIn("[" + other + "]", text)
            # Windowsでもファイルが閉じられていることを確認
            path.rename(path.with_suffix(".checked"))

    def test_initial_read_failure_is_saved(self):
        self.cap.read.return_value = (False, None)
        with self.assertRaises(ConnectionError):
            self.record(enabled=True)
        path = next(self.root.rglob("*.txt"))
        self.assertIn("error: ConnectionError", path.read_text())
        path.rename(path.with_suffix(".checked"))

    def test_log_open_failure_does_not_stop_recording(self):
        with patch("builtins.open", side_effect=PermissionError()):
            self.assertTrue(self.record(enabled=True))
        self.writer.write.assert_called()

    def test_log_write_failure_closes_log_and_continues(self):
        log = Mock()
        log.write.side_effect = OSError()
        with patch("builtins.open", return_value=log):
            self.assertTrue(self.record(enabled=True))
        log.close.assert_called_once()
        self.writer.write.assert_called()


if __name__ == "__main__":
    unittest.main()