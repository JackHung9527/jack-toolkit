"""USB-HID 測試工具 — 進入點。

host 端 HID 終端機：列舉系統上的 HID 裝置、開啟指定 collection（VID/PID +
usage page）、收 Input report、送 Output report、Get/Set Feature report，
HEX / ASCII 雙模式並附 log。適合測試自製 HID 裝置（例如 STM32 custom HID）。

獨立執行：
    python main.py
也可經 jack-toolkit launcher 啟動（本目錄含 manifest.json）。
需要第三方套件 hidapi（Windows wheel 自帶 hidapi.dll，走 OS 內建 HID driver，
不需要 Zadig 換 driver）；請先跑專案根目錄的 install_requirements.bat。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在其他 import 之前裝好 ===
# 用 pythonw.exe（雙擊/釘選）跑時 stderr 被吃掉，未捕捉例外會「靜默死掉」沒線索。
_ERROR_LOG = Path(__file__).resolve().parent / "usbhid_error.log"


def _global_excepthook(exc_type, exc_value, exc_tb) -> None:
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        _ERROR_LOG.write_text(tb_text, encoding="utf-8")
    except OSError:
        pass

    # 缺 hidapi 時給出明確的安裝指引。
    hint = ""
    if isinstance(exc_value, ModuleNotFoundError) and exc_value.name == "hid":
        hint = ("\n\n看起來缺少 hidapi，請先在系統 Python 安裝：\n"
                "    python -m pip install hidapi\n"
                "或直接跑專案根目錄的 install_requirements.bat。")
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror(
            "USB-HID 測試工具啟動失敗",
            f"Traceback 已寫到:\n{_ERROR_LOG}\n\n錯誤摘要:\n{tb_text[-1500:]}{hint}",
        )
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import tkinter as tk

from app import HidApp

HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "usbhid.ico"


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _center_window(win) -> None:
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(ICO_PATH))
    except Exception:
        pass
    HidApp(root)
    _center_window(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
