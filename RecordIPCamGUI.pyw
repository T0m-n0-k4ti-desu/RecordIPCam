import argparse

if __name__ == '__main__':
    try:
        from module.RecorderGUI import OpenGUI
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", default="IPCAM_USER.json")
        parser.add_argument("--output", default="")
        args = parser.parse_args()
        OpenGUI(args.config, args.output)
    except Exception as error:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("起動エラー", type(error).__name__ + ": 録画GUIを起動できませんでした。")
        root.destroy()