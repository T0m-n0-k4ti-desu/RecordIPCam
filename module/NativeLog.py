import os
import ctypes
import sys
import threading
import uuid


"""
 起動用プロセスから転送されたネイティブ標準エラーを取得
"""
class NativeCapture:
    def __init__(self):
        self.lock = threading.RLock()
        self.callbacks = set()
        self.barriers = {}
        self.active = False

    def register(self, callback):
        with self.lock:
            self.callbacks.add(callback)

    def unregister(self, callback):
        self.drain()
        with self.lock:
            self.callbacks.discard(callback)

    def start(self, notify):
        if self.active:
            return
        if os.environ.get("IPCAM_NATIVE_PIPE") != "1" or sys.stdin is None:
            raise OSError("Native capture requires RecordIPCamGUI.pyw launcher.")
        self.notify = notify
        self.runtimes = []
        if os.name == "nt":
            for name in ("msvcrt.dll", "ucrtbase.dll"):
                runtime = ctypes.CDLL(name)
                runtime.fflush.argtypes = [ctypes.c_void_p]
                runtime.fflush.restype = ctypes.c_int
                self.runtimes.append(runtime)
        self.source = sys.stdin.buffer
        self.stop_token = "__IPCAM_STOP_" + uuid.uuid4().hex
        self.active = True
        self.thread = threading.Thread(target=self.read, name="NativeStderr", daemon=True)
        self.thread.start()
        self.finished = threading.Event()
        self.flusher = threading.Thread(target=self.flush_loop, name="NativeFlush", daemon=True)
        self.flusher.start()

    def dispatch(self, line):
        with self.lock:
            barrier = self.barriers.get(line)
            callbacks = tuple(self.callbacks)
        if barrier is not None:
            barrier.set()
            return
        if not line.strip() or line.startswith("__IPCAM_"):
            return
        message = "[FFmpeg/shared stderr] " + line
        for callback in callbacks:
            try:
                callback(message)
            except Exception:
                self.notify("Native log destination failure.")
        self.notify(message)

    def read(self):
        while True:
            # 改行のない出力も一度に読み込む量を制限
            data = self.source.readline(8192)
            if not data:
                break
            line = data.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == self.stop_token:
                break
            self.dispatch(line)

    def flush(self):
        for runtime in self.runtimes:
            runtime.fflush(None)

    def flush_loop(self):
        # 長い録画中もCランタイムのバッファを定期的に書き出す
        while not self.finished.wait(1):
            self.flush()

    def drain(self):
        if not self.active or not self.thread.is_alive():
            return
        self.flush()
        token = "__IPCAM_LOG_" + uuid.uuid4().hex
        event = threading.Event()
        with self.lock:
            self.barriers[token] = event
        try:
            os.write(2, ("\n" + token + "\n").encode("ascii"))
            event.wait(timeout=2)
        except OSError:
            pass
        finally:
            with self.lock:
                self.barriers.pop(token, None)

    def stop(self):
        if not self.active:
            return
        self.finished.set()
        self.flusher.join(timeout=2)
        self.drain()
        try:
            os.write(2, ("\n" + self.stop_token + "\n").encode("ascii"))
        except OSError:
            pass
        self.thread.join(timeout=3)
        self.active = False


capture = NativeCapture()