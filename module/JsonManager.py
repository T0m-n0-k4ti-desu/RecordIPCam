import json
import os
import tempfile
import threading
import ipaddress
from urllib.parse import quote
from module import CamNetwork

json_lock = threading.Lock()

"""
 Jsonファイルの読み込み
"""
def OpenJson(filepath):
    with open(filepath, 'r', encoding='utf-8') as json_file:
        return json.load(json_file)

"""
 RTSPのアドレスをParse
"""
def ParseRTSP_FromJson(cam_dict):
    user_id = quote(cam_dict['user_id'], safe='')
    user_pw = quote(cam_dict['user_pw'], safe='')
    host_ip = cam_dict['host_ip']
    rtsp_addr = f"rtsp://{user_id}:{user_pw}@{host_ip}/stream1"

    return {"cam_name":cam_dict["cam_name"], "rtsp_addr":rtsp_addr,
            "mac_addr":CamNetwork.NormalizeMAC(cam_dict.get("mac_addr", ""))}

"""
  JsonからRTSPのアドレスを作成
"""
def CreateRTSPADDR_FromJson(filepath):
    userdata = OpenJson(filepath)
    rtsp_addr = []
    for camdata in userdata["cams"]:
        addr = ParseRTSP_FromJson(camdata)
        addr["json_path"] = os.path.abspath(filepath)
        rtsp_addr.append(addr)

    return rtsp_addr

"""
 発見したIPを読み込み元のJsonに保存
"""
def UpdateHostIP_FromMAC(filepath, camname, mac_addr, host_ip):
    target = CamNetwork.NormalizeMAC(mac_addr)
    if not target:
        raise ValueError("MAC address is required.")
    ipaddress.IPv4Address(host_ip)
    # 読み直しから保存まで排他制御し、別カメラの更新を保持
    with json_lock:
        userdata = OpenJson(filepath)
        matches = [
            cam for cam in userdata["cams"]
            if cam.get("cam_name") == camname
            and CamNetwork.NormalizeMAC(cam.get("mac_addr", "")) == target
        ]
        if len(matches) != 1:
            raise ValueError("Camera entry is missing or ambiguous.")
        if matches[0]["host_ip"] == host_ip:
            return False
        matches[0]["host_ip"] = host_ip

        # 同じフォルダの一時ファイルへ保存後に置換(失敗時は元を保持)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=os.path.dirname(os.path.abspath(filepath)),
                prefix='.ipcam_', suffix='.tmp', delete=False
            ) as json_file:
                temp_path = json_file.name
                json.dump(userdata, json_file, ensure_ascii=False, indent=4)
                json_file.write('\n')
                json_file.flush()
                os.fsync(json_file.fileno())
            os.replace(temp_path, filepath)
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)
    return True