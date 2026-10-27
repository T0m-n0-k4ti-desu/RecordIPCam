import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


class NativeLogTests(unittest.TestCase):
    def test_real_ffmpeg_warning_is_saved_in_movie_log(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            script = folder / "probe.py"
            script.write_text("""
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import cv2, numpy as np
from module import NativeLog, ThreadManager as tm
from module import gloval_value as g
root=pathlib.Path(sys.argv[2])
bad=root/'bad.mp4'
bad.write_bytes(bytes.fromhex('000000186674797069736f6d0000020069736f6d69736f32'))
messages=[]
NativeLog.capture.start(messages.append)
g.thread_running=True
class Camera:
    def get(self, key):
        return 15
    def read(self):
        if not hasattr(self,'warned'):
            self.warned=True
            c=cv2.VideoCapture(str(bad),cv2.CAP_FFMPEG)
            c.release()
        return True,np.zeros((48,64,3),dtype=np.uint8)
try:
    tm.RecMovie(Camera(),str(root/'movie'),'camera',0.01,1,save_log=True)
finally:
    NativeLog.capture.stop()
assert not NativeLog.capture.thread.is_alive()
assert not NativeLog.capture.flusher.is_alive()
assert not NativeLog.capture.callbacks
(root/'result.json').write_text(json.dumps(messages))
""", encoding="utf-8")
            environment = os.environ.copy()
            environment["IPCAM_NATIVE_PIPE"] = "1"
            process = subprocess.Popen(
                [sys.executable, str(script), str(Path(__file__).resolve().parents[1]), str(folder)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            raw = []
            def forward():
                try:
                    while True:
                        data = process.stderr.readline(8192)
                        if not data:
                            break
                        raw.append(data)
                        process.stdin.write(data)
                        process.stdin.flush()
                except (OSError, BrokenPipeError):
                    pass
            reader = threading.Thread(target=forward, daemon=True)
            reader.start()
            try:
                self.assertEqual(process.wait(timeout=20), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                reader.join(timeout=3)
                process.stdin.close()
                process.stderr.close()
            messages = json.loads((folder / "result.json").read_text())
            self.assertTrue(any("moov atom not found" in item for item in messages), (messages, raw))
            logfile = next((folder / "movie").rglob("*.txt"))
            text = logfile.read_text(encoding="utf-8")
            self.assertIn("[FFmpeg/shared stderr]", text)
            self.assertIn("moov atom not found", text)
            self.assertNotIn("__IPCAM_LOG_", text)
            self.assertTrue(logfile.with_suffix(".mp4").is_file())


    def test_shared_output_reaches_only_registered_logs(self):
        from module.NativeLog import NativeCapture
        capture = NativeCapture()
        first, second, gui = [], [], []
        capture.notify = gui.append
        capture.register(first.append)
        capture.register(second.append)
        capture.dispatch("native warning")
        capture.unregister(first.append)
        capture.dispatch("next warning")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 2)
        self.assertEqual(len(gui), 2)
        self.assertTrue(all("[FFmpeg/shared stderr]" in item for item in second))

if __name__ == "__main__":
    unittest.main()