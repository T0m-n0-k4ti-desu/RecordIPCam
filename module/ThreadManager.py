import cv2
import time
import threading
import datetime
import math
import os
from urllib.parse import urlsplit

# 自作moduleのimport
from module import CamTime
from module import CamCap
from module import CamNetwork
from module import JsonManager
from module import FileManager
from module import NativeLog
from module import gloval_value as g


"""
 録画機能
"""
def RecMovie(cap, movie_root_path, cam_name, time_sec, acceptabletime, fps = 15, status_callback = None, save_log = False):
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

    # カメラ・動画ごとに専用のログを開く(GUIの表示上限とは独立)
    log_file = None
    if save_log:
        try:
            log_file = open(os.path.splitext(filepath)[0] + '.txt', 'a', encoding='utf-8')
        except OSError as error:
            print(f"[{cam_name}]\t Log opening failure: {type(error).__name__}")

    log_lock = threading.RLock()
    def write_file(message):
        nonlocal log_file
        with log_lock:
            if log_file is not None:
                try:
                    stamp = datetime.datetime.now().isoformat(timespec='seconds')
                    log_file.write(f"{stamp}\t[{cam_name}]\t{message}\n")
                    log_file.flush()
                except OSError as error:
                    # ログ保存に失敗しても録画を継続
                    try:
                        log_file.close()
                    except OSError:
                        pass
                    log_file = None
                    print(f"[{cam_name}]\t Log writing failure: {type(error).__name__}")

    def write_log(message):
        print(f"[{cam_name}]\t{message}")
        write_file(message)

    if log_file is not None:
        NativeLog.capture.register(write_file)

    video = None
    frames_written = 0
    time_start = time.monotonic()
    result = "stopped"
    try:
        write_log(f"FilePath: {filepath}")
        write_log(f"Record Time: {time_sec}s")
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
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        video = cv2.VideoWriter()
        video.open(filepath, fourcc, fps, (w, h))
        if not video.isOpened():
            raise OSError(f"[{cam_name}]\t Video file opening failure.")
        write_log(f"Width: {w}, Height: {h}, FPS: {fps}")
        write_log("--- Record Start! ---")
        if status_callback:
            status_callback("録画中", filepath)

        # 時計の補正に影響されない経過時間でファイルを分割
        time_start = time.monotonic()
        while g.thread_running:
            if time.monotonic() - time_start >= time_sec:
                result = "completed"
                break
            if frame.shape[:2] != (h, w):
                raise ValueError(f"[{cam_name}]\t Frame size changed.")
            video.write(frame)
            frames_written += 1
            cap_ret, frame = cap.read()
            if not g.thread_running:
                return False
            if not cap_ret or frame is None:
                raise ConnectionError(f"[{cam_name}]\t Frame loading failure.")
            if time.monotonic() - time_start > time_sec + acceptabletime:
                raise TimeoutError(f"[{cam_name}]\t Recording time exceeded.")
        return g.thread_running
    except Exception as error:
        result = "error: " + type(error).__name__
        write_log("Recording failure: " + type(error).__name__)
        raise
    finally:
        try:
            if video is not None:
                video.release()
        finally:
            write_log(f"Result: {result}; Frames submitted: {frames_written}; Elapsed: {time.monotonic() - time_start:.3f}s")
            write_log("--- Record Stop! ---")
            NativeLog.capture.unregister(write_file)
            with log_lock:
                if log_file is not None:
                    try:
                        log_file.close()
                    except OSError as error:
                        print(f"[{cam_name}]\t Log closing failure: {type(error).__name__}")
                    finally:
                        log_file = None

"""
  実際にスレッドで動かす処理
"""
def CamThreadFunc(camname, addr, rectime, acceptabletime, mac_addr = "", json_path = None, movie_root_path = None, status_callback = None, save_log = False):
    cap = None
    search_next = 0
    # 保存先の明示指定を優先し、省略時はJsonの場所を基準にする
    if movie_root_path is None:
        base_path = os.path.dirname(os.path.abspath(json_path)) if json_path else os.getcwd()
        movie_root_path = os.path.join(base_path, "movie")
    movie_root_path = os.path.abspath(movie_root_path)
    try:
        while g.thread_running:
            try:
                if cap is None:
                    if status_callback:
                        status_callback("接続中", "")
                    cap = CamCap.OpenCap(camname, addr)
                if not RecMovie(cap, movie_root_path, camname, rectime, acceptabletime, status_callback=status_callback, save_log=save_log):
                    break
            except Exception as e:
                if not g.thread_running:
                    break
                if status_callback:
                    status_callback("再接続待機: " + type(e).__name__, "")
                # 接続失敗も含めて再試行(認証情報は表示しない)
                print(f"[{camname}]\t Recording failure: {type(e).__name__}")
                CamCap.CloseCap(camname, cap)
                cap = None
                # MAC指定時は接続先を再探索(失敗が続いても探索は60秒間隔)
                if mac_addr and time.monotonic() >= search_next:
                    try:
                        print(f"[{camname}]\t Searching camera by MAC address.")
                        host_ip = CamNetwork.FindIP_FromMAC(mac_addr, urlsplit(addr).hostname)
                        if host_ip:
                            addr = CamNetwork.ReplaceRTSPHost(addr, host_ip)
                            print(f"[{camname}]\t Camera address found: {host_ip}")
                            if json_path:
                                try:
                                    if JsonManager.UpdateHostIP_FromMAC(json_path, camname, mac_addr, host_ip):
                                        print(f"[{camname}]\t Camera address saved to JSON.")
                                except Exception as save_error:
                                    # 保存失敗でも発見したIPでの再接続は継続
                                    print(f"[{camname}]\t JSON update failure: {type(save_error).__name__}")
                        else:
                            print(f"[{camname}]\t Camera address not found.")
                    except Exception as search_error:
                        # 探索できない場合も元の接続先で再試行を続ける
                        print(f"[{camname}]\t Search failure: {type(search_error).__name__}")
                    search_next = time.monotonic() + 60
                for i in range(50):
                    if not g.thread_running:
                        break
                    time.sleep(0.1)
    finally:
        CamCap.CloseCap(camname, cap)
        if status_callback:
            status_callback("停止", "")

"""
  カメラスレッドの作成
"""
def CamThreadCreate(camname, addr, rectime, acceptabletime, mac_addr = "", json_path = None, movie_root_path = None, status_callback = None, save_log = False):
    return threading.Thread(target=CamThreadFunc, args=(camname, addr, rectime, acceptabletime, mac_addr, json_path, movie_root_path, status_callback, save_log))

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
