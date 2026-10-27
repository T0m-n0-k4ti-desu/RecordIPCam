import argparse
import concurrent.futures
import glob
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile

import cv2
import numpy as np


"""
 動画から抜粋画像を作成(録画処理とは独立)
"""
def CreateContactSheet(filepath, output = None, interval = 60, count = None,
                       columns = 4, width = 480, rows = 8, save_frames = False):
    if columns < 1 or rows < 1 or not 120 <= width <= 1920 or columns * width > 16000:
        raise ValueError("Invalid image dimensions.")
    if columns * rows * width * (round(width * 9 / 16) + 54) > 40000000:
        raise ValueError("Page is too large.")
    if count is not None and not 1 <= count <= 10000:
        raise ValueError("Count must be between 1 and 10000.")
    if count is None and (not math.isfinite(interval) or interval <= 0):
        raise ValueError("Interval must be positive.")

    filepath = Path(filepath).resolve()
    cap = cv2.VideoCapture(str(filepath))
    temporary = None
    # Windows版OpenCVが日本語パスを開けない場合は一時パスを利用
    if not cap.isOpened() and filepath.is_file() and not str(filepath).isascii():
        cap.release()
        temporary = tempfile.TemporaryDirectory(prefix="video_contact_")
        alias = Path(temporary.name) / ("input" + filepath.suffix)
        try:
            try:
                os.link(filepath, alias)
            except OSError:
                shutil.copyfile(filepath, alias)
            cap = cv2.VideoCapture(str(alias))
        except BaseException:
            temporary.cleanup()
            raise
    directory = None
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open video.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or frames < 1:
            raise ValueError("Video FPS or frame count is unavailable.")
        duration = frames / fps
        if count is not None:
            targets = np.linspace(0, frames - 1, min(count, frames), dtype=np.int64).tolist()
        else:
            number = math.ceil(duration / interval)
            if number > 10000:
                raise ValueError("More than 10000 samples requested. Increase interval.")
            targets = sorted({min(int(i * interval * fps), frames - 1) for i in range(number)})

        base = Path(output).resolve() if output else filepath.parent / "contact_sheets"
        base.mkdir(parents=True, exist_ok=True)
        # 同名動画や再実行でも既存の結果を上書きしない
        key = hashlib.sha256(str(filepath).encode('utf-8')).hexdigest()[:8]
        directory = Path(tempfile.mkdtemp(prefix=filepath.stem[:60] + '_' + key + '_', dir=str(base)))
        height = round(width * 9 / 16)
        tile_height = height + 54
        page_size = columns * rows
        tiles = []
        samples = []
        pages = []
        errors = []
        if save_frames:
            (directory / "frames").mkdir()

        def save_image(path, image):
            # 日本語を含む保存先にも対応
            ok, encoded = cv2.imencode(path.suffix, image)
            if not ok:
                raise OSError("Image encoding failed.")
            path.write_bytes(encoded.tobytes())

        def save_page():
            if not tiles:
                return
            used_rows = math.ceil(len(tiles) / columns)
            sheet = np.full((used_rows * tile_height, columns * width, 3), 24, dtype=np.uint8)
            for i, tile in enumerate(tiles):
                y, x = (i // columns) * tile_height, (i % columns) * width
                sheet[y:y + tile_height, x:x + width] = tile
            name = f"contact_sheet_{len(pages) + 1:03d}.jpg"
            save_image(directory / name, sheet)
            pages.append(name)
            tiles.clear()

        for target in targets:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, target):
                errors.append(dict(requested_frame=int(target), error="Seek failed"))
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                errors.append(dict(requested_frame=int(target), error="Read failed"))
                continue
            # 読み込み後の位置は次フレームなので1を引く
            actual = max(0, round(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1)
            seconds = actual / fps
            millis = round(seconds * 1000)
            hours, rest = divmod(millis, 3600000)
            minutes, rest = divmod(rest, 60000)
            secs, ms = divmod(rest, 1000)
            timestamp = f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
            h, w = frame.shape[:2]
            scale = min(width / w, height / h)
            resized = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))))
            tile = np.full((tile_height, width, 3), 24, dtype=np.uint8)
            rh, rw = resized.shape[:2]
            y, x = (height - rh) // 2, (width - rw) // 2
            tile[y:y + rh, x:x + rw] = resized
            font_scale = min(0.55, width / 650)
            cv2.putText(tile, timestamp, (8, height + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(tile, f"Frame {actual} (0-based)", (8, height + 43),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
            page = len(pages) + 1
            slot = len(tiles)
            sample = dict(requested_frame=int(target), frame=actual, seconds=seconds,
                          timestamp=timestamp, page=page, row=slot // columns + 1,
                          column=slot % columns + 1)
            if save_frames:
                name = f"frames/frame_{actual:09d}.jpg"
                save_image(directory / name, frame)
                sample["image"] = name
            samples.append(sample)
            tiles.append(tile)
            if len(tiles) == page_size:
                save_page()
        save_page()
        report = dict(video=str(filepath), fps=fps, frame_count=frames,
                      duration_seconds=duration, interval_seconds=interval if count is None else None,
                      requested_count=count, pages=pages, samples=samples, errors=errors,
                      time_basis="Frame index / nominal FPS; not camera clock or exact VFR timestamps.")
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=4), encoding='utf-8')
        if not samples:
            raise ValueError(f"No frames extracted. Report: {directory}")
        return directory, len(samples), len(errors)
    finally:
        cap.release()
        if temporary is not None:
            temporary.cleanup()


"""
 複数動画を順番に処理
"""
def ProcessFiles(files, options, notify = print):
    failures = 0
    for filepath in files:
        notify(f"Processing: {filepath}")
        try:
            directory, samples, errors = CreateContactSheet(filepath, **options)
            notify(f"Saved: {directory} ({samples} images, {errors} skipped)")
            if errors:
                failures += 1
        except Exception as error:
            failures += 1
            notify(f"Failed: {filepath}: {error}")
    return failures


"""
 引数なしで起動した場合のGUI
"""
def OpenGUI(initial_files = None):
    import queue
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except ImportError:
        DND_FILES = None
        root = tk.Tk()
    else:
        root = TkinterDnD.Tk()
    root.title("動画の抜粋画像一覧")
    root.geometry("760x560")
    selected = []
    events = queue.Queue()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    busy = False
    mode = tk.StringVar(value="interval")
    value = tk.StringVar(value="60")
    columns = tk.StringVar(value="4")
    output = tk.StringVar()
    save_frames = tk.BooleanVar(value=False)

    def add_files(files):
        for file in files:
            path = str(Path(file).resolve())
            if Path(path).is_file() and path not in selected:
                selected.append(path)
                listing.insert(tk.END, path)

    def drop(event):
        if not busy:
            # Tclのリストとして解析し、空白・日本語を含むパスを保持
            add_files(root.tk.splitlist(event.data))
        return "copy"

    def remove_selected():
        if not busy:
            for index in reversed(listing.curselection()):
                del selected[index]
                listing.delete(index)

    def choose():
        files = filedialog.askopenfilenames(filetypes=[("動画", "*.mp4 *.mkv *.avi *.mov *.ts *.m4v"), ("すべて", "*.*")])
        if not busy:
            add_files(files)

    def browse():
        folder = filedialog.askdirectory()
        if folder:
            output.set(folder)

    controls = ttk.Frame(root, padding=12)
    controls.pack(fill="x")
    ttk.Button(controls, text="動画を選択（複数可）", command=choose).pack(anchor="w")
    ttk.Button(controls, text="選択した動画を削除", command=remove_selected).pack(anchor="w")
    ttk.Label(controls, text="下の一覧に動画をドラッグ＆ドロップ（複数可）" if DND_FILES else "D&Dを使う場合：pip install tkinterdnd2").pack(anchor="w")
    listing = tk.Listbox(root, height=6, selectmode=tk.EXTENDED)
    listing.pack(fill="x", padx=12)
    if DND_FILES:
        listing.drop_target_register(DND_FILES)
        listing.dnd_bind('<<Drop>>', drop)
    add_files(initial_files or [])
    settings = ttk.Frame(root, padding=12)
    settings.pack(fill="x")
    ttk.Radiobutton(settings, text="間隔（秒）", variable=mode, value="interval").grid(row=0, column=0)
    ttk.Radiobutton(settings, text="枚数（動画全体から均等）", variable=mode, value="count").grid(row=0, column=1)
    ttk.Entry(settings, textvariable=value, width=10).grid(row=0, column=2)
    ttk.Label(settings, text="列数").grid(row=1, column=0)
    ttk.Entry(settings, textvariable=columns, width=10).grid(row=1, column=1)
    ttk.Label(settings, text="保存先（空欄：各動画の隣のcontact_sheets）").grid(row=2, column=0, columnspan=3, sticky="w")
    ttk.Entry(settings, textvariable=output, width=65).grid(row=3, column=0, columnspan=2)
    ttk.Button(settings, text="参照", command=browse).grid(row=3, column=2)
    ttk.Checkbutton(settings, text="元解像度の抜粋画像も保存", variable=save_frames).grid(row=4, column=0, columnspan=3, sticky="w")
    log = tk.Text(root, height=10, state="disabled")
    log.pack(fill="both", expand=True, padx=12, pady=8)

    def run():
        nonlocal busy
        if not selected:
            messagebox.showerror("入力確認", "動画を選択してください。")
            return
        try:
            number = float(value.get())
            cols = int(columns.get())
            if not math.isfinite(number) or number <= 0 or not 1 <= cols <= 16:
                raise ValueError()
            if mode.get() == "count" and (not number.is_integer() or number > 10000):
                raise ValueError()
        except ValueError:
            messagebox.showerror("入力確認", "間隔は正の秒数、枚数は1～10000の整数、列数は1～16で指定してください。")
            return
        options = dict(output=output.get() or None, columns=cols, save_frames=save_frames.get(),
                       interval=number if mode.get() == "interval" else 60,
                       count=int(number) if mode.get() == "count" else None)
        busy = True
        start.configure(state="disabled")
        future = executor.submit(ProcessFiles, list(selected), options, events.put)
        def completed(job):
            try:
                events.put(("done", job.result()))
            except Exception as error:
                events.put(str(error))
                events.put(("done", 1))
        future.add_done_callback(completed)

    def poll():
        nonlocal busy
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, tuple):
                busy = False
                start.configure(state="normal")
                event = f"完了（エラーまたは一部抽出失敗の動画：{event[1]}件）"
            log.configure(state="normal")
            log.insert("end", event + "\n")
            log.see("end")
            log.configure(state="disabled")
        root.after(100, poll)

    def close():
        if busy:
            messagebox.showinfo("処理中", "処理が完了してから閉じてください。")
            return
        executor.shutdown(wait=False)
        root.destroy()

    start = ttk.Button(root, text="作成", command=run)
    start.pack(pady=8)
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="動画を一定間隔または指定枚数で抜粋し、画像一覧を作成")
    parser.add_argument("videos", nargs="*", help="動画ファイル（複数・ワイルドカード可）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interval", type=float, default=60, help="抜粋間隔の秒数（既定60）")
    mode.add_argument("--count", type=int, help="動画全体から均等に抜粋する枚数")
    parser.add_argument("--output", help="出力先（既定：動画の隣のcontact_sheets）")
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--width", type=int, default=480, help="1画像の幅")
    parser.add_argument("--rows", type=int, default=8, help="1ページの最大行数")
    parser.add_argument("--save-frames", action="store_true", help="元解像度の抜粋も保存")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if args.gui or not args.videos:
        # WindowsではGUIをpythonwで起動し、コンソールを残さない
        if os.name == 'nt' and Path(sys.executable).stem.lower() != 'pythonw':
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            if not pythonw.is_file():
                parser.error("pythonw.exe was not found. Use ViewoSplitterGUI.pyw.")
            subprocess.Popen(
                [str(pythonw), str(Path(__file__).resolve().with_name("ViewoSplitterGUI.pyw")), *args.videos],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return 0
        OpenGUI(args.videos)
        return 0
    files = []
    for pattern in args.videos:
        matches = sorted(glob.glob(pattern)) if glob.has_magic(pattern) else [pattern]
        if not matches:
            parser.error(f"No files matched: {pattern}")
        for file in matches:
            if file not in files:
                files.append(file)
    return int(ProcessFiles(files, dict(output=args.output, interval=args.interval, count=args.count,
                                        columns=args.columns, width=args.width, rows=args.rows,
                                        save_frames=args.save_frames)) > 0)


if __name__ == "__main__":
    raise SystemExit(main())