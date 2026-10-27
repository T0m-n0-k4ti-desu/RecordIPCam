import cv2
import time
import threading
import datetime
import math
import os

# 自作moduleのimport
from module import CamTime
from module import CamCap
from module import FileManager
from module import gloval_value as g


"""
 録画機能
"""
def RecMovie(cap, movie_root_path, cam_name, time_sec, acceptabletime, fps = 15):
    if not g.thread_running:
        return False
    if time_sec <= 0:
        raise ValueError(f"[{cam_name}]\t Invalid record time.")

    now = datetime.datetime.now()
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M%S_%f')

    dirpath = os.path.join(movie_root_path, date_str)
    filepath = os.path.join(dirpath, cam_name + '_' + date_str + '_' + time_str + '.mp4')
    FileManager.Mkdir(dirpath, filepath)

    # カメラのFPSを使用(取得できない場合は既定値)
    cap_fps = cap.get(cv2.CAP_PROP_FPS)
    if math.isfinite(cap_fps) and cap_fps > 0:
        fps = cap_fps

    # 最初のフレームでサイズと取得状態を確認
    cap_ret, frame = cap.read()
    if not g.thread_running:
        return False
    if not cap_ret or frame is None:
        raise ConnectionError(f"[{cam_name}]\t Frame loading failure.")
    h, w = frame.shape[:2]

    # 動画保存時の形式を設定
    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
    video = cv2.VideoWriter()
    try:
        video.open(filepath, fourcc, fps, (w, h))
        if not video.isOpened():
            raise OSError(f"[{cam_name}]\t Video file opening failure.")

        print(f"[{cam_name}]\tFilePath: {filepath}")
        print(f"[{cam_name}]\tWidth: {w}, Height: {h}, FPS: {fps}")
        print(f"[{cam_name}]\tRecord Time    : {time_sec}s")
        print(f"[{cam_name}]\t--- Record Start! ---")

        # 時計の補正に影響されない経過時間でファイルを分割
        time_start = time.monotonic()
        while g.thread_running:
            if time.monotonic() - time_start >= time_sec:
                break
            if frame.shape[:2] != (h, w):
                raise ValueError(f"[{cam_name}]\t Frame size changed.")
            video.write(frame)

            cap_ret, frame = cap.read()
            if not g.thread_running:
                return False
            if not cap_ret or frame is None:
                raise ConnectionError(f"[{cam_name}]\t Frame loading failure.")
            if time.monotonic() - time_start > time_sec + acceptabletime:
                raise TimeoutError(f"[{cam_name}]\t Recording time exceeded.")
    finally:
        # 取得失敗・停止時も動画ファイルを閉じる
        video.release()
        print(f"[{cam_name}]\t--- Record Stop! ---")

    return g.thread_running

"""
  実際にスレッドで動かす処理
"""
def CamThreadFunc(camname, addr, rectime, acceptabletime):
    cap = None
    movie_root_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "movie")
    try:
        while g.thread_running:
            try:
                if cap is None:
                    cap = CamCap.OpenCap(camname, addr)
                if not RecMovie(cap, movie_root_path, camname, rectime, acceptabletime):
                    break
            except Exception as e:
                if not g.thread_running:
                    break
                # 接続失敗も含めて再試行(認証情報は表示しない)
                print(f"[{camname}]\t Recording failure: {type(e).__name__}")
                CamCap.CloseCap(camname, cap)
                cap = None
                for i in range(50):
                    if not g.thread_running:
                        break
                    time.sleep(0.1)
    finally:
        CamCap.CloseCap(camname, cap)

"""
  カメラスレッドの作成
"""
def CamThreadCreate(camname, addr, rectime, acceptabletime):
    return threading.Thread(target=CamThreadFunc, args=(camname, addr, rectime, acceptabletime))

"""
  スレッドを止める用の処理
"""
def CamTreadClose(cam_threads):
    try:
        while any(cam_thread.is_alive() for cam_thread in cam_threads):
            time.sleep(0.1)
    except KeyboardInterrupt:
        # Press '[ctrl] + [c]'
        pass
    finally:
        g.thread_running = False
        for cam_thread in cam_threads:
            cam_thread.join()
        cv2.destroyAllWindows()
