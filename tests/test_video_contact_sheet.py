import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from VideoContactSheet import CreateContactSheet, ProcessFiles


class ContactSheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "input.mp4"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        self.assertTrue(writer.isOpened())
        try:
            for i in range(30):
                writer.write(np.full((48, 64, 3), i * 5, dtype=np.uint8))
        finally:
            writer.release()

    def tearDown(self):
        self.temp.cleanup()

    def test_interval_and_labels(self):
        directory, number, errors = CreateContactSheet(self.video, interval=1, width=240)
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([s["frame"] for s in report["samples"]], [0, 10, 20])
        self.assertEqual([s["timestamp"] for s in report["samples"]],
                         ["00:00:00.000", "00:00:01.000", "00:00:02.000"])
        self.assertEqual((number, errors), (3, 0))

    def test_count_pages_and_original_frames(self):
        directory, number, errors = CreateContactSheet(
            self.video, count=5, columns=2, rows=2, width=240, save_frames=True
        )
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(number, 5)
        self.assertEqual(len(report["pages"]), 2)
        self.assertEqual(report["samples"][-1]["frame"], 29)
        self.assertEqual(len(list((directory / "frames").glob("*.jpg"))), 5)

    def test_japanese_paths_and_layout(self):
        renamed = self.video.with_name("動画.mp4")
        self.video.rename(renamed)
        directory, number, errors = CreateContactSheet(
            renamed, output=self.root / "画像", count=1, width=240, columns=1
        )
        image = cv2.imdecode(np.fromfile(str(directory / "contact_sheet_001.jpg"), dtype=np.uint8), 1)
        self.assertEqual(image.shape[:2], (189, 240))
        self.assertEqual(number, 1)

    def test_no_overwrite(self):
        first, _, _ = CreateContactSheet(self.video, count=1)
        second, _, _ = CreateContactSheet(self.video, count=1)
        self.assertNotEqual(first, second)
        self.assertTrue((first / "report.json").exists())

    def test_batch_continues_after_failure(self):
        messages = []
        failures = ProcessFiles([self.root / "missing.mp4", self.video], dict(count=1), messages.append)
        self.assertEqual(failures, 1)
        self.assertTrue(any(message.startswith("Saved:") for message in messages))

    def test_invalid_options(self):
        for options in [dict(interval=0), dict(count=0), dict(columns=0),
                        dict(width=10000), dict(interval=float("nan"))]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                CreateContactSheet(self.video, **options)

    def test_short_video(self):
        _, number, _ = CreateContactSheet(self.video)
        self.assertEqual(number, 1)

    def test_seek_failure_is_recorded(self):
        original = cv2.VideoCapture
        class FailedSeek:
            def __init__(self, path):
                self.cap = original(path)
            def isOpened(self):
                return self.cap.isOpened()
            def get(self, key):
                return self.cap.get(key)
            def set(self, key, value):
                return False
            def release(self):
                self.cap.release()
        with patch("VideoContactSheet.cv2.VideoCapture", FailedSeek):
            with self.assertRaises(ValueError):
                CreateContactSheet(self.video, count=1)
        report = next((self.root / "contact_sheets").rglob("report.json"))
        self.assertEqual(len(json.loads(report.read_text())["errors"]), 1)


    @unittest.skipUnless(os.name == "nt", "Windows GUI launcher")
    def test_gui_uses_pythonw(self):
        import VideoContactSheet as app
        with patch.object(sys, "argv", ["VideoContactSheet.py", "--gui", "space name.mp4"]), patch.object(app.subprocess, "Popen") as launch:
            self.assertEqual(app.main(), 0)
            command = launch.call_args.args[0]
            self.assertEqual(Path(command[0]).name.lower(), "pythonw.exe")
            self.assertTrue(command[1].endswith(".pyw"))
            self.assertEqual(command[2], "space name.mp4")
            self.assertEqual(launch.call_args.kwargs["creationflags"], app.subprocess.CREATE_NO_WINDOW)

    def test_cli_keeps_console_processing(self):
        import VideoContactSheet as app
        with patch.object(sys, "argv", ["VideoContactSheet.py", str(self.video)]), patch.object(app, "ProcessFiles", return_value=0) as process, patch.object(app.subprocess, "Popen") as launch:
            self.assertEqual(app.main(), 0)
            process.assert_called_once()
            launch.assert_not_called()

if __name__ == "__main__":
    unittest.main()