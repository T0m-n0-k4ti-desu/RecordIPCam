import os
from pathlib import Path
import queue
import sys
import threading
import time

from module import CamTime, JsonManager, ThreadManager, NativeLog
from module import gloval_value as g


"""
 GUI用の録画セッション(全カメラの終了まで再起動しない)
"""
class RecorderSession:
    def __init__(self):
        self.threads = []
        self.cameras = []
        self.output = None

    def is_running(self):
        return any(thread.is_alive() for thread in self.threads)

    def start(self, config, output, seconds, notify, save_log = False):
        if self.is_running():
            raise RuntimeError("録画または停止処理が進行中です。")
        if not 1 <= seconds <= 86400:
            raise ValueError("分割時間は1秒～24時間で指定してください。")
        json_path = str(Path(config).resolve())
        cameras = JsonManager.CreateRTSPADDR_FromJson(json_path)
        if not cameras:
            raise ValueError("カメラが設定されていません。")
        names = [cam["cam_name"] for cam in cameras]
        if len(set(names)) != len(names):
            raise ValueError("カメラ名が重複しています。")
        if any(not isinstance(name, str) or not name or any(c in name for c in '\/:*?"<>|') for name in names):
            raise ValueError("カメラ名にはファイル名に使用できる文字を指定してください。")
        self.output = str(Path(output).resolve()) if output else str(Path(json_path).parent / "movie")
        Path(self.output).mkdir(parents=True, exist_ok=True)
        self.cameras = cameras
        self.threads = []
        g.thread_running = True
        try:
            for index, cam in enumerate(cameras):
                def status(state, filepath, index=index):
                    notify(("status", index, state, filepath))
                thread = ThreadManager.CamThreadCreate(
                    cam["cam_name"], cam["rtsp_addr"], seconds, CamTime.GetAcceptableTime(seconds),
                    cam["mac_addr"], cam["json_path"], self.output, status, save_log
                )
                thread.start()
                self.threads.append(thread)
        except Exception:
            g.thread_running = False
            raise

    def stop(self):
        g.thread_running = False


"""
 ログを無制限に蓄積しないGUI用出力
"""
class QueueLog:
    def __init__(self, events):
        self.events = events
        self.buffer = ""
        self.lock = threading.Lock()

    def write(self, text):
        with self.lock:
            # printの断片や改行なしの出力でも保持量を制限
            self.buffer = (self.buffer + str(text))[-8192:]
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                if line.strip():
                    try:
                        self.events.put_nowait(("log", line))
                    except queue.Full:
                        pass
        return len(text)

    def flush(self):
        pass


"""
 録画GUI
"""
def OpenGUI(config = "IPCAM_USER.json", output = ""):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except ImportError:
        root = tk.Tk()
        DND_FILES = None
    else:
        root = TkinterDnD.Tk()
    root.title("RecordIPCam — 録画")
    root.geometry("980x650")
    root.minsize(760, 500)
    session = RecorderSession()
    events = queue.Queue(maxsize=1000)
    config_var = tk.StringVar(value=str(Path(config).resolve()))
    output_var = tk.StringVar(value=output)
    minutes_var = tk.StringVar(value=str(CamTime.GetRecTime() / 60))
    save_log_var = tk.BooleanVar(value=False)
    summary_var = tk.StringVar(value="停止中")
    started = None
    stopping = False
    closing = False

    def send(event):
        try:
            events.put_nowait(event)
        except queue.Full:
            pass

    panel = ttk.Frame(root, padding=12)
    panel.pack(fill="x")
    panel.columnconfigure(1, weight=1)

    def choose_json():
        name = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if name:
            config_var.set(name)

    def choose_output():
        folder = filedialog.askdirectory()
        if folder:
            output_var.set(folder)

    ttk.Label(panel, text="カメラ設定JSON").grid(row=0, column=0, sticky="w", pady=5)
    config_entry = ttk.Entry(panel, textvariable=config_var)
    config_entry.grid(row=0, column=1, sticky="ew", padx=8)
    config_button = ttk.Button(panel, text="参照", command=choose_json)
    config_button.grid(row=0, column=2)
    ttk.Label(panel, text="保存先（空欄：JSONの隣のmovie）").grid(row=1, column=0, sticky="w", pady=5)
    output_entry = ttk.Entry(panel, textvariable=output_var)
    output_entry.grid(row=1, column=1, sticky="ew", padx=8)
    output_button = ttk.Button(panel, text="参照", command=choose_output)
    output_button.grid(row=1, column=2)
    ttk.Label(panel, text="1ファイルの録画時間（分）").grid(row=2, column=0, sticky="w", pady=5)
    minutes_entry = ttk.Entry(panel, textvariable=minutes_var, width=12)
    minutes_entry.grid(row=2, column=1, sticky="w", padx=8)
    log_check = ttk.Checkbutton(panel, text="動画ごとにテキストログを保存", variable=save_log_var)
    log_check.grid(row=3, column=1, sticky="w", padx=8, pady=5)
    if DND_FILES:
        def drop(event):
            if not session.is_running():
                files = root.tk.splitlist(event.data)
                if len(files) == 1 and Path(files[0]).suffix.lower() == ".json":
                    config_var.set(files[0])
            return "copy"
        config_entry.drop_target_register(DND_FILES)
        config_entry.dnd_bind("<<Drop>>", drop)
    inputs = [config_entry, output_entry, minutes_entry, config_button, output_button, log_check]

    buttons = ttk.Frame(root, padding=(12, 0))
    buttons.pack(fill="x")
    tree = ttk.Treeview(root, columns=("name", "state", "file"), show="headings", height=7)
    for name, title, width in [("name", "カメラ", 140), ("state", "状態", 180), ("file", "保存中のファイル", 540)]:
        tree.heading(name, text=title)
        tree.column(name, width=width)
    tree.pack(fill="x", padx=12, pady=10)
    ttk.Label(root, textvariable=summary_var).pack(anchor="w", padx=12)
    log = tk.Text(root, height=14, state="disabled", wrap="word")
    log.pack(fill="both", expand=True, padx=12, pady=10)

    def append_log(line):
        log.configure(state="normal")
        log.insert("end", line + "\n")
        lines = int(log.index("end-1c").split(".")[0])
        if lines > 500:
            log.delete("1.0", f"{lines - 500}.0")
        log.see("end")
        log.configure(state="disabled")

    def set_controls(active):
        for widget in inputs:
            widget.configure(state="disabled" if active else "normal")
        start_button.configure(state="disabled" if active else "normal")
        stop_button.configure(state="normal" if active else "disabled")

    def start():
        nonlocal started, stopping
        if session.is_running():
            return
        # 前セッションの通知を除去してから表示を初期化
        while not events.empty():
            events.get_nowait()
        for item in tree.get_children():
            tree.delete(item)
        try:
            seconds = float(minutes_var.get()) * 60
            if not config_var.get().strip():
                raise ValueError("設定JSONを選択してください。")
            session.start(config_var.get(), output_var.get().strip(), seconds, send, save_log=save_log_var.get())
        except Exception as error:
            # 設定値やRTSP認証情報をエラーダイアログに出さない
            messagebox.showerror("録画開始失敗", f"設定JSON・保存先・分割時間を確認してください。\n{type(error).__name__}")
            if not session.is_running():
                set_controls(False)
                return
            session.stop()
        for index, cam in enumerate(session.cameras):
            tree.insert("", "end", iid=str(index), values=(cam["cam_name"], "接続待機", ""))
        started = time.monotonic()
        stopping = False
        set_controls(True)
        append_log("録画開始 / 保存先: " + session.output)

    def stop():
        nonlocal stopping
        stopping = True
        session.stop()
        stop_button.configure(state="disabled")
        summary_var.set("停止処理中：動画ファイルとカメラ接続の終了を待っています")
        append_log("停止要求を送信しました。")

    def open_output():
        folder = session.output or output_var.get() or str(Path(config_var.get()).resolve().parent / "movie")
        if not Path(folder).is_dir():
            messagebox.showinfo("保存先", "保存先フォルダはまだ作成されていません。")
            return
        if os.name == "nt":
            os.startfile(folder)

    start_button = ttk.Button(buttons, text="録画開始", command=start)
    start_button.pack(side="left", padx=(0, 8))
    stop_button = ttk.Button(buttons, text="停止", command=stop, state="disabled")
    stop_button.pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="保存先を開く", command=open_output).pack(side="left")

    def close():
        nonlocal closing
        if session.is_running():
            if not messagebox.askyesno("録画を終了", "録画を停止して閉じますか？"):
                return
            closing = True
            stop()
        else:
            root.destroy()

    def poll():
        nonlocal started, stopping
        for _ in range(200):
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "log":
                append_log(event[1])
            elif event[0] == "status":
                _, index, state, file = event
                if tree.exists(str(index)):
                    values = tree.item(str(index), "values")
                    tree.item(str(index), values=(values[0], state, file))
        running = session.is_running()
        if started is not None:
            if running and not stopping:
                elapsed = int(time.monotonic() - started)
                summary_var.set(f"録画セッション稼働中 / 経過 {elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}")
            elif not running:
                for index, thread in enumerate(session.threads):
                    thread.join()
                    if tree.exists(str(index)):
                        values = tree.item(str(index), "values")
                        tree.item(str(index), values=(values[0], "停止", ""))
                started = None
                stopping = False
                summary_var.set("停止中")
                set_controls(False)
                append_log("全カメラの停止が完了しました。")
        if closing and not running:
            root.destroy()
            return
        root.after(100, poll)

    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = QueueLog(events)
    try:
        NativeLog.capture.start(lambda message: send(("log", message)))
    except OSError as error:
        send(("log", "Native stderr capture failure: " + type(error).__name__))
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    try:
        root.mainloop()
    finally:
        session.stop()
        for thread in session.threads:
            thread.join()
        NativeLog.capture.stop()
        sys.stdout, sys.stderr = original_stdout, original_stderr