import os
import sys

# スクリプトのディレクトリパスをsys.pathに追加
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# 自作moduleのimport
from module import CamTime
from module import JsonManager
from module import ThreadManager
from module import gloval_value as g

# スレッドが動いているかどうかのフラグ
g.thread_running = True

"""
  動画録画(Ctrl+Cで終了)
"""
if __name__ == '__main__':
    rectime = CamTime.GetRecTime()
    acceptabletime = CamTime.GetAcceptableTime(rectime)
    addrs = JsonManager.CreateRTSPADDR_FromJson(os.path.join(os.path.dirname(__file__), 'IPCAM_USER.json'))

    cam_threads = []
    cam_maxnum = len(addrs)

    # カメラ数分のスレッド起動
    for i in range(cam_maxnum):
        cam_threads.append(ThreadManager.CamThreadCreate(addrs[i]["cam_name"], addrs[i]["rtsp_addr"], rectime, acceptabletime))
        cam_threads[i].start()

    # スレッド停止用の処理で待機
    ThreadManager.CamTreadClose(cam_threads)