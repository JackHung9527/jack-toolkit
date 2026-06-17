"""小算盤 — 多模式計算機（仿 Windows）。

模式：標準 / 工程 / 程式設計師(16,10,8,2 進位 + 位元運算) / 浮點數(IEEE 754) / CRC。
tkinter 實作，運算引擎與 UI 解耦（engine_*.py / ui_*.py）。純標準函式庫，無第三方依賴。

獨立執行：
    python main.py
也可經 jack-toolkit launcher 啟動（本目錄含 manifest.json）。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在其他 import 之前裝好 ===
# 用 pythonw.exe（雙擊/釘選）跑時 stderr 被吃掉，未捕捉例外會「靜默死掉」。
_ERROR_LOG = Path(__file__).resolve().parent / "calculator_error.log"


def _global_excepthook(exc_type, exc_value, exc_tb) -> None:
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        _ERROR_LOG.write_text(tb_text, encoding="utf-8")
    except OSError:
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror(
            "小算盤啟動失敗",
            f"Traceback 已寫到:\n{_ERROR_LOG}\n\n錯誤摘要:\n{tb_text[-1500:]}",
        )
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import tkinter as tk

import theme
from ui_standard import StandardFrame
from ui_scientific import ScientificFrame
from ui_programmer import ProgrammerFrame
from ui_float import FloatFrame
from ui_crc import CrcFrame

HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "calculator.ico"

MODES = [
    ("標準", StandardFrame),
    ("工程", ScientificFrame),
    ("程式", ProgrammerFrame),
    ("浮點數", FloatFrame),
    ("CRC", CrcFrame),
]


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.frames: dict[str, tk.Frame] = {}
        self.nav_btns: dict[str, tk.Button] = {}
        self.current: tk.Frame | None = None

        root.title("小算盤")
        root.configure(bg=theme.BG)
        root.geometry("560x660")
        root.minsize(480, 600)
        try:
            root.iconbitmap(default=str(ICO_PATH))
        except Exception:
            pass

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # 模式導覽列
        nav = tk.Frame(root, bg=theme.BG)
        nav.grid(row=0, column=0, sticky="ew", padx=4, pady=(6, 0))
        for i in range(len(MODES)):
            nav.columnconfigure(i, weight=1)
        for i, (name, _cls) in enumerate(MODES):
            b = tk.Button(nav, text=name, command=(lambda n=name: self.show(n)),
                          bg=theme.BG, fg=theme.NAV_FG, activebackground=theme.NAV_ACTIVE_BG,
                          activeforeground=theme.NAV_ACTIVE_FG, relief="flat", bd=0,
                          font=(theme.UI, 11), cursor="hand2", takefocus=0)
            b.grid(row=0, column=i, sticky="nsew", padx=1, pady=2)
            self.nav_btns[name] = b

        # 內容容器
        self.container = tk.Frame(root, bg=theme.BG)
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        # 全域鍵盤分派到目前分頁
        root.bind("<Key>", self._on_key)

        self.show("標準")
        _center_window(root)

    def _frame(self, name: str) -> tk.Frame:
        if name not in self.frames:
            cls = dict(MODES)[name]
            frame = cls(self.container)
            frame.grid(row=0, column=0, sticky="nsew")
            self.frames[name] = frame
        return self.frames[name]

    def show(self, name: str) -> None:
        frame = self._frame(name)
        frame.tkraise()
        self.current = frame
        for n, b in self.nav_btns.items():
            on = (n == name)
            b.configure(bg=theme.NAV_ACTIVE_BG if on else theme.BG,
                        fg=theme.NAV_ACTIVE_FG if on else theme.NAV_FG,
                        font=(theme.UI, 11, "bold") if on else (theme.UI, 11))
        # 有輸入框的模式（浮點數 / CRC）把焦點給輸入框，其餘給 root 用全域鍵盤。
        # 立即設一次，並延後到事件佇列清空後再設一次：nav 按鈕點擊/模式切換會造成
        # 焦點副作用，若只同步設定，切過去後「第一個按鍵」會被送到別處而遺失
        # （例如剛切到浮點數時第一個小數點打不進去）。
        focus_widget = getattr(frame, "focus_widget", None)
        target = focus_widget if focus_widget is not None else self.root
        target.focus_set()
        self.root.after_idle(target.focus_set)

    def _on_key(self, event: tk.Event) -> None:
        # Ctrl+1..5 切換模式（即使焦點在輸入框也可用）
        if (event.state & 0x4) and event.keysym in ("1", "2", "3", "4", "5"):
            idx = int(event.keysym) - 1
            if 0 <= idx < len(MODES):
                self.show(MODES[idx][0])
            return
        # 焦點在輸入框（Entry）時放行，交給 Entry 原生處理，避免吞掉小數點等字元
        if isinstance(event.widget, tk.Entry):
            return
        if self.current is not None and hasattr(self.current, "on_key"):
            self.current.on_key(event.keysym, event.char)


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _center_window(win) -> None:
    """把視窗置中於螢幕（在 mainloop 前呼叫，視窗一出現就在中央）。"""
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
