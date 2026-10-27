import argparse
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
    parser = argparse.ArgumentParser(description="IPカメラの録画")
    parser.add_argument("--config", default="IPCAM_USER.json", help="設定JSONのパス")
    parser.add_argument("--output", help="動画の保存先(省略時はJSONと同じ場所のmovie)")
    args = parser.parse_args()

    # 相対パスは起動時の作業ディレクトリを基準にする
    json_path = os.path.abspath(args.config)
    movie_root_path = os.path.abspath(args.output) if args.output is not None else os.path.join(os.path.dirname(json_path), "movie")

    rectime = CamTime.GetRecTime()
    acceptabletime = CamTime.GetAcceptableTime(rectime)
    addrs = JsonManager.CreateRTSPADDR_FromJson(json_path)

    cam_threads = []
    cam_maxnum = len(addrs)

    # カメラ数分のスレッド起動
    for i in range(cam_maxnum):
        cam_threads.append(ThreadManager.CamThreadCreate(addrs[i]["cam_name"], addrs[i]["rtsp_addr"], rectime, acceptabletime, addrs[i]["mac_addr"], addrs[i]["json_path"], movie_root_path))
        cam_threads[i].start()

    # スレッド停止用の処理で待機
    ThreadManager.CamTreadClose(cam_threads)