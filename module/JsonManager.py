import json
from urllib.parse import quote

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

    return {"cam_name":cam_dict["cam_name"], "rtsp_addr":rtsp_addr}

"""
  JsonからRTSPのアドレスを作成
"""
def CreateRTSPADDR_FromJson(filepath):
    userdata = OpenJson(filepath)
    rtsp_addr = []
    for camdata in userdata["cams"]:
        rtsp_addr.append(ParseRTSP_FromJson(camdata))

    return rtsp_addr
