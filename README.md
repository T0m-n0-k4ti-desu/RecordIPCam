# RecordIPCam

RTSP対応のIPカメラをOpenCVで録画します。カメラごとにスレッドを起動し、
MP4ファイルに分割して保存します。Ctrl+Cで録画を終了します。

## 実行環境

- Python 3
- OpenCVのPythonパッケージ(opencv-python)。FFmpeg対応ビルドが必要です。
- MACアドレスによるIP探索と安定性確認ツールはWindows向けです。

## カメラ設定

作業ディレクトリに IPCAM_USER.json を作成します。
cams にカメラごとの設定を追加してください。

    {
        "cams": [
            {
                "cam_name": "camera_1",
                "user_id": "rtsp_user",
                "user_pw": "rtsp_password",
                "host_ip": "192.168.1.10",
                "mac_addr": ""
            }
        ]
    }

- cam_name: 動画ファイル名に使うカメラ名。ファイル名に使える文字を指定します。
- user_id / user_pw: カメラのRTSP認証情報。
- host_ip: カメラのIPv4アドレス。
- mac_addr: IP探索に使うMACアドレス。省略または空文字で探索を無効にします。
  指定例は AA:BB:CC:DD:EE:FF または AA-BB-CC-DD-EE-FF です。

接続先は rtsp://ユーザー名:パスワード@host_ip/stream1 です。

## 起動と保存先

起動した作業ディレクトリの IPCAM_USER.json を読み込みます。
動画の既定の保存先は、読み込んだJSONと同じ場所にある movie フォルダです。
保存先フォルダは自動作成します。

    python /path/to/RecordIPCam.py

JSONと動画の保存先は、それぞれオプションで指定できます。
相対パスは作業ディレクトリを基準に解決します。

    python /path/to/RecordIPCam.py --config ./settings/cameras.json
    python /path/to/RecordIPCam.py --output ./recordings
    python /path/to/RecordIPCam.py --config ./settings/cameras.json --output ./recordings

| 指定 | 読み込むJSON | 動画の保存先 |
| --- | --- | --- |
| 指定なし | 作業ディレクトリ/IPCAM_USER.json | 作業ディレクトリ/movie |
| --config ./settings/cameras.json | 作業ディレクトリ/settings/cameras.json | 作業ディレクトリ/settings/movie |
| --output ./recordings | 作業ディレクトリ/IPCAM_USER.json | 作業ディレクトリ/recordings |
| 両方指定 | --config のファイル | --output のフォルダ |

動画は保存先/日付/カメラ名_日付_時刻.mp4 の形式で保存します。
分割時間は module/CamTime.py の record_h、record_m、record_s で設定します。
既定は15分です。保存FPSにはカメラから取得した値を使い、取得できない場合は15を使います。
カメラの申告FPSと実際の取得速度に差がある場合、録画時間と再生時間にずれが生じます。
録画ファイルの自動削除機能はありません。

## 接続失敗時の動作

接続のタイムアウトは10秒、フレーム取得のタイムアウトは5秒です。
接続・録画に失敗すると接続を解放し、5秒待って再試行します。
動画ファイルは停止時やエラー時にも閉じます。

mac_addr が設定されている場合、接続・録画の失敗時に同じローカルIPv4サブネットを
ARPで探索し、MACアドレスが一致するIPへ接続先を変更します。
発見したIPは、読み込んだJSONのカメラ名とMACアドレスが一致する項目の host_ip にも保存します。
JSONの保存に失敗しても、発見したIPへの再接続を継続します。
探索が終了してから60秒間は再探索せず、保持しているIPへの接続を試みます。

探索にはWindows標準のPowerShellとSendARPを使います。
探索範囲は最大1024アドレスです。別サブネットや端末間通信が禁止されたWi-Fi、
カメラが電源OFFの状態などでは発見できません。
映像の受信状況によっては、FFmpegのデコードエラーが表示されることがあります。

## 安定性確認ツール

Windowsでは、次のコマンドで実カメラの反復録画・再接続試験を実行できます。

    python tools/check_stability.py --config ./IPCAM_USER.json --seconds 120 --segment 2 --reconnect-every 10

各カメラを同時に録画し、指定回数のファイル分割ごとに接続を解放し、
5秒待って再接続します。設定JSONの更新やMAC探索は行いません。
試験動画は一時フォルダに保存して削除します。確認用動画は残しません。

メモリ(Private Bytes・Working Set・Python割り当て量)、Windowsハンドル数、
Pythonスレッド数は作業ディレクトリの test_recordings/memory_report.json に記録します。
結果ファイルは --report で指定できます。Ctrl+Cでも終了できます。
本番と同時に試験する場合は、カメラの同時接続数を確認してください。

短時間の反復試験だけでは2～3日の安定動作は判断できません。
長時間運転では、メモリの増加傾向と保存ドライブの空き容量を確認してください。

## 動画の抜粋画像一覧

VideoContactSheet.py は録画処理と独立したツールです。
動画から静止画を抜粋し、時刻とフレーム番号を添えたJPEGの一覧画像を作成します。
元の動画は変更しません。OpenCVとNumPyを使用し、GUIにはTkinterが必要です。D&Dには tkinterdnd2 を使用します。

    python -m pip install -r requirements-contact-sheet.txt

引数なしで起動するとGUIを開きます。Windowsではpythonwに切り替え、GUI用のコンソールを残しません。
エクスプローラーから一覧へ複数の動画をドラッグ＆ドロップできます。選択ボタンからの追加も可能です。
同じ動画は重複追加せず、一覧で選択した動画は削除ボタンで外せます。
複数動画、秒数または枚数、列数、保存先、
元解像度の抜粋画像の保存を選択できます。

    python VideoContactSheet.py

GUI専用の入口は VideoContactSheet.pyw です。
.pyw がPythonに関連付けられた環境では、ダブルクリックでコンソールを開かずに起動できます。
ターミナルからは次のコマンドでも起動できます。

    pythonw VideoContactSheet.pyw

tkinterdnd2 が未インストールの場合は選択ボタンで動画を追加できます。
動画を引数に指定するコマンドライン実行では、ログとエラーをコンソールに表示します。

コマンドラインからも実行できます。

    python VideoContactSheet.py video.mp4
    python VideoContactSheet.py video.mp4 --interval 60
    python VideoContactSheet.py video.mp4 --count 12
    python VideoContactSheet.py video1.mp4 video2.mp4 --count 20 --columns 5
    python VideoContactSheet.py "./movie/20261027/*.mp4" --output ./sheets --save-frames

- --interval: 抜粋間隔(秒)。既定は60秒で、動画の先頭から1分ごとに抜粋します。
- --count: 動画全体から均等に抜粋する枚数。先頭と末尾を含み、1枚なら先頭のみです。
  フレーム数より多く指定した場合はフレーム数までに制限します。
  --interval とは同時指定できません。1動画の最大抜粋数は10000枚です。
- --columns: 一覧の列数。既定は4です。
- --width: 1画像の幅。既定は480ピクセルです。縦横比を保ち、余白を付けて配置します。
- --rows: 1ページの最大行数。既定は8です。超えた分は次のJPEGへ分けます。
- --output: 保存先。省略時は各動画と同じ場所の contact_sheets フォルダです。
- --save-frames: 一覧に加え、元解像度の抜粋JPEGも frames フォルダへ保存します。
- --gui: GUIを開きます。

出力先には動画ごとの専用フォルダを作成し、再実行時も既存の結果は上書きしません。
contact_sheet_001.jpg などの一覧画像と、抽出位置・エラーを記録した report.json を保存します。
画像内の時刻は動画先頭からの経過時間、フレーム番号は0始まりです。
経過時間はフレーム番号と申告FPSから計算するため、可変FPS動画では目安になります。
映像に焼き込まれたカメラの日時を読み取る機能はありません。
抽出できなかった位置はJSONへ記録し、複数動画はエラーがあっても次の動画へ進みます。
このツールは抜粋位置だけを読み込むため、全フレームの破損検査には使えません。

Windows版OpenCVで日本語の動画パスを直接開けない場合、一時パスから読み込みます。
同一ドライブでハードリンクを作れない場合は一時コピーを作るため、動画分の空き容量が必要です。
一時ファイルは処理後に削除します。

自動テストは次のコマンドで実行できます。

    python -m unittest discover -s tests -p test_video_contact_sheet.py -v
