import argparse
import contextlib
import ctypes
from ctypes import wintypes
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from module import CamCap, JsonManager, ThreadManager
from module import gloval_value as g


class MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t)
    ]


def main():
    parser = argparse.ArgumentParser(description="Windows camera recording stability test")
    parser.add_argument("--config", required=True)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--segment", type=float, default=2)
    parser.add_argument("--reconnect-every", type=int, default=10)
    parser.add_argument("--report", default="test_recordings/memory_report.json")
    args = parser.parse_args()
    if args.seconds <= 0 or args.segment <= 0 or args.reconnect_every < 1:
        parser.error("Durations and reconnect interval must be positive")

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    process = kernel.GetCurrentProcess()
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    memory_api = ctypes.WinDLL("psapi", use_last_error=True)
    memory_api.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD
    ]

    def sample():
        gc.collect()
        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handles = wintypes.DWORD()
        if not memory_api.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.GetProcessHandleCount(process, ctypes.byref(handles)):
            raise ctypes.WinError(ctypes.get_last_error())
        current, peak = tracemalloc.get_traced_memory()
        return dict(seconds=round(time.monotonic() - start, 2),
                    private_mb=round(counters.PrivateUsage / 1024 ** 2, 2),
                    working_mb=round(counters.WorkingSetSize / 1024 ** 2, 2),
                    python_mb=round(current / 1024 ** 2, 2),
                    handles=handles.value, threads=threading.active_count())

    cams = JsonManager.CreateRTSPADDR_FromJson(args.config)
    if not cams:
        parser.error("No cameras configured")
    cv2.setLogLevel(0)
    g.thread_running = True
    tracemalloc.start()
    start = time.monotonic()
    deadline = start + args.seconds
    results = [dict(camera=i + 1, segments=0, connections=0, errors=[]) for i in range(len(cams))]

    def retry_wait():
        # 本番と同じ5秒待機で、短時間の接続集中を避ける
        for _ in range(50):
            if not g.thread_running or time.monotonic() >= deadline:
                break
            time.sleep(0.1)

    def worker(index, cam, root):
        cap = None
        stats = results[index]
        try:
            while g.thread_running and time.monotonic() < deadline:
                try:
                    if cap is None:
                        cap = CamCap.OpenCap("test_" + str(index + 1), cam["rtsp_addr"])
                        stats["connections"] += 1
                    if not ThreadManager.RecMovie(
                        cap, root, "test_" + str(index + 1), args.segment, 10
                    ):
                        break
                    stats["segments"] += 1
                    # 検証動画は一時保存し、ファイル増加によるディスク消費を抑える
                    for path in Path(root).rglob("*.mp4"):
                        path.unlink()
                    if stats["segments"] % args.reconnect_every == 0:
                        cap.release()
                        cap = None
                        retry_wait()
                except Exception as error:
                    # 長時間試験でもエラーの履歴を無制限に蓄積しない
                    if len(stats["errors"]) < 20:
                        stats["errors"].append(type(error).__name__)
                    if cap is not None:
                        cap.release()
                        cap = None
                    retry_wait()
        finally:
            if cap is not None:
                cap.release()

    samples = []
    # ライブラリのログは蓄積せず破棄し、計測結果だけファイルへ保存
    with tempfile.TemporaryDirectory(prefix="ipcam_stability_") as root, open(os.devnull, "w") as log:
        with contextlib.redirect_stdout(log):
            threads = [
                threading.Thread(target=worker, args=(i, cam, str(Path(root) / str(i))))
                for i, cam in enumerate(cams)
            ]
            for thread in threads:
                thread.start()
            try:
                while any(thread.is_alive() for thread in threads):
                    samples.append(sample())
                    for _ in range(100):
                        if not any(thread.is_alive() for thread in threads):
                            break
                        time.sleep(0.1)
            except KeyboardInterrupt:
                pass
            finally:
                g.thread_running = False
                for thread in threads:
                    thread.join()
            samples.append(sample())
    report = dict(duration_seconds=round(time.monotonic() - start, 2),
                  results=results, samples=samples)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(item["errors"] or item["segments"] == 0 for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())