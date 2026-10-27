import argparse
import os
from pathlib import Path
import subprocess
import sys


"""
 DLLが標準エラーを初期化する前に取得用のパイプを接続
"""
def RunWithNativeLog(arguments):
    python = Path(sys.executable).with_name("python.exe") if os.name == "nt" else Path(sys.executable)
    environment = os.environ.copy()
    environment["IPCAM_NATIVE_PIPE"] = "1"
    process = subprocess.Popen(
        [str(python), str(Path(__file__).resolve()), "--native-child", *arguments],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env=environment
    )
    try:
        while True:
            data = process.stderr.readline(8192)
            if not data:
                break
            try:
                process.stdin.write(data)
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                break
    finally:
        process.stdin.close()
        process.stderr.close()
    return process.wait()


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", default="IPCAM_USER.json")
        parser.add_argument("--output", default="")
        parser.add_argument("--native-child", action="store_true", help=argparse.SUPPRESS)
        args = parser.parse_args()
        if args.native_child:
            from module.RecorderGUI import OpenGUI
            OpenGUI(args.config, args.output)
        else:
            raise SystemExit(RunWithNativeLog(sys.argv[1:]))
    except Exception as error:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("起動エラー", type(error).__name__ + ": 録画GUIを起動できませんでした。")
        root.destroy()