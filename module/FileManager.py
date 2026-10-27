import os

"""
 ディレクトリの作成
"""
def Mkdir(dirpath, filepath):
    # 親フォルダも作成(複数スレッドからの同時作成を許容)
    os.makedirs(dirpath, exist_ok=True)
