import cv2
import time

from module import gloval_value as g

# 接続・フレーム取得のタイムアウト(ミリ秒)
open_timeout_msec = 10000
read_timeout_msec = 5000

"""
 キャプチャ開始(Close忘れ注意)
"""
def OpenCap(camname, rtsp_addr):
    # タイムアウトを指定できるFFmpegでRTSP経由動画
    cap = cv2.VideoCapture()
    try:
        cap.open(rtsp_addr, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout_msec,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, read_timeout_msec
        ])
        if not cap.isOpened():
            raise ConnectionError(f"[{camname}]\t Camera connection failure.")
    except Exception:
        cap.release()
        raise
    print(f"[{camname}]\t*** Open Capture! ***")
    return cap

"""
 キャプチャ終了(Close後に再度実行しても問題なし)
"""
def CloseCap(camname, cap):
    if cap is not None:
        cap.release()
        print(f"[{camname}]\t*** Close Capture! ***")

"""
  キャプチャを開きなおす
"""
def ReOpenCap(camname, cap, rtsp_addr):
    CloseCap(camname, cap)
    # 再接続まで待機(停止命令があれば待機を終了)
    for i in range(50):
        if not g.thread_running:
            return None
        time.sleep(0.1)
    return OpenCap(camname, rtsp_addr)
