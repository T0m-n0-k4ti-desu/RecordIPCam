# RecordIPCam
## Usage
1. Camera Configuration
Edit the IPCAM_USER.json file to configure your IP cameras.  
An example configuration for one camera is provided.  
You can configure multiple cameras by separating them with " , ".   
[Note] that a thread will be generated for each camera.  
``` json
{
  "cams":[
        {
            "cam_name":"your camera name",
            "user_id":"rtsp id",
            "user_pw":"rtsp password",
            "host_ip":"rtsp ip addr",
            "mac_addr":"AA:BB:CC:DD:EE:FF"
        }
    ]
}
```
2. Start the Script
Run the Python script with the following command:
``` bash
$ python3 RecordIPCam.py
```

## Note
During operation, you may encounter the following error.  
This occurs when the IP camera fails to retrieve frames. Currently, there is no easy workaround for this issue. Please be aware of this limitation.
``` bash
error while decoding MB xxx xxx, bytestream xxx
```
## MACアドレスによる再接続
Windowsでは、各カメラの設定に省略可能な mac_addr を追加できます。
AA:BB:CC:DD:EE:FF または AA-BB-CC-DD-EE-FF の形式で指定してください。
省略または空文字の場合は、従来どおり host_ip で再接続します。

接続・録画処理に失敗すると、host_ip と同じローカルIPv4サブネットを
ARPで探索し、MACアドレスが一致するIPへ接続先を変更します。
発見したIPは読み込み元JSONの該当カメラの host_ip にも保存します。
カメラ名とMACアドレスが両方一致する項目のみ更新します。
保存できない場合はログを表示し、発見したIPでの再接続を継続します。
探索が終了してから60秒間は再探索せず、通常の再接続を続けます。

探索にはWindows標準のPowerShellとSendARPを使います。追加ライブラリは不要です。
探索範囲は最大1024アドレスです。別サブネット、端末間通信が禁止されたWi-Fi、
カメラが電源OFFの状態などでは発見できません。
探索できない場合も、保持しているIPへの再接続は継続します。