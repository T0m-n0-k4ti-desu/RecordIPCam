import sys

# pythonwで実行するGUI専用の入口
if __name__ == '__main__':
    try:
        from ViewoSplitter import OpenGUI
        OpenGUI(sys.argv[1:])
    except Exception as error:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("起動エラー", str(error))
        root.destroy()