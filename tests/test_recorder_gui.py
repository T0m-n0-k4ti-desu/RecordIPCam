import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from module import RecorderGUI as gui, ThreadManager as tm
from module import gloval_value as g


class RecorderGUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "cameras.json"
        self.config.write_text(json.dumps({"cams": [
            dict(cam_name="one", user_id="u", user_pw="p", host_ip="192.0.2.1"),
            dict(cam_name="two", user_id="u", user_pw="p", host_ip="192.0.2.2")
        ]}), encoding="utf-8")
        self.session = gui.RecorderSession()

    def tearDown(self):
        self.session.stop()
        for thread in self.session.threads:
            thread.join(timeout=3)
        self.temp.cleanup()

    def test_start_stop_and_restart(self):
        def run(*args):
            while g.thread_running:
                time.sleep(0.01)
        with patch.object(tm, "CamThreadCreate", side_effect=lambda *args: threading.Thread(target=run)):
            self.session.start(self.config, "", 900, lambda event: None)
            self.assertTrue(self.session.is_running())
            self.assertEqual(self.session.output, str(self.root / "movie"))
            with self.assertRaises(RuntimeError):
                self.session.start(self.config, "", 900, lambda event: None)
            self.session.stop()
            for thread in self.session.threads:
                thread.join(timeout=3)
            self.assertFalse(self.session.is_running())
            self.session.start(self.config, str(self.root / "custom"), 30, lambda event: None)
            self.assertEqual(self.session.output, str(self.root / "custom"))

    def test_bad_duration(self):
        for seconds in (0, float("nan"), 86401):
            with self.assertRaises(ValueError):
                self.session.start(self.config, "", seconds, lambda event: None)

    def test_empty_config(self):
        self.config.write_text('{"cams":[]}')
        with self.assertRaises(ValueError):
            self.session.start(self.config, "", 900, lambda event: None)

    def test_name_validation(self):
        data = json.loads(self.config.read_text())
        data["cams"][0]["cam_name"] = "../outside"
        self.config.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.session.start(self.config, "", 900, lambda event: None)

    def test_partial_start_failure_is_stoppable(self):
        def run():
            while g.thread_running:
                time.sleep(0.01)
        fail = Mock()
        fail.start.side_effect = RuntimeError()
        with patch.object(tm, "CamThreadCreate", side_effect=[threading.Thread(target=run), fail]):
            with self.assertRaises(RuntimeError):
                self.session.start(self.config, "", 900, lambda event: None)
        self.assertFalse(g.thread_running)
        self.assertEqual(len(self.session.threads), 1)

    def test_status_callbacks(self):
        events = []
        def record(*args, **kwargs):
            kwargs["status_callback"]("recording", "test.mp4")
            return False
        with patch.object(tm.CamCap, "OpenCap", return_value=Mock()), patch.object(tm.CamCap, "CloseCap"), patch.object(tm, "RecMovie", side_effect=record):
            self.session.start(self.config, "", 900, events.append)
            for thread in self.session.threads:
                thread.join(timeout=3)
        self.assertEqual({event[1] for event in events}, {0, 1})
        self.assertEqual(sum(event[2] == "recording" for event in events), 2)
        self.assertEqual(sum(event[2] == "停止" for event in events), 2)

    def test_log_is_bounded(self):
        events = queue.Queue(maxsize=2)
        sink = gui.QueueLog(events)
        sink.write("one\ntwo\nthree\n")
        self.assertEqual(events.qsize(), 2)
        sink.write("x" * 100000)
        self.assertLessEqual(len(sink.buffer), 8192)


    def test_real_writer_stops_and_produces_readable_video(self):
        import cv2
        import numpy as np
        data = json.loads(self.config.read_text())
        data["cams"] = data["cams"][:1]
        self.config.write_text(json.dumps(data))
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        cap = Mock()
        cap.get.return_value = 15
        def read():
            time.sleep(0.02)
            return True, frame.copy()
        cap.read.side_effect = read
        events = []
        with patch.object(tm.CamCap, "OpenCap", return_value=cap):
            self.session.start(self.config, "", 60, events.append)
            deadline = time.monotonic() + 3
            while not any(event[2] == "録画中" for event in events) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(any(event[2] == "録画中" for event in events))
            time.sleep(0.1)
            self.session.stop()
            for thread in self.session.threads:
                thread.join(timeout=3)
        self.assertFalse(self.session.is_running())
        output = next((self.root / "movie").rglob("*.mp4"))
        check = cv2.VideoCapture(str(output))
        try:
            ok, image = check.read()
            self.assertTrue(ok)
            self.assertEqual(image.shape[:2], (48, 64))
        finally:
            check.release()
        cap.release.assert_called_once()

if __name__ == "__main__":
    unittest.main()