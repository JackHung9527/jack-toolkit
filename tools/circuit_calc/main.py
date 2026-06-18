"""電路計算機 — 多模式電子電路計算工具。

上方下拉選單切換計算項目，每個項目附參考電路圖；所有數值欄位皆可切換單位
（Ω mΩ µΩ … / V mV µV … 等）。運算引擎與 UI 解耦（engine.py / units.py /
schematic.py / base_frame.py / ui_*.py）。純標準函式庫，無第三方依賴。

獨立執行：
    python main.py
也可經 jack-toolkit launcher 啟動（本目錄含 manifest.json）。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在其他 import 之前裝好 ===
# 用 pythonw.exe（雙擊/釘選）跑時 stderr 被吃掉，未捕捉例外會「靜默死掉」沒線索。
_ERROR_LOG = Path(__file__).resolve().parent / "circuit_calc_error.log"


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
            "電路計算機啟動失敗",
            f"Traceback 已寫到:\n{_ERROR_LOG}\n\n錯誤摘要:\n{tb_text[-1500:]}",
        )
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import tkinter as tk
from tkinter import ttk

import theme
from ui_divider import DividerFrame
from ui_units import UnitsFrame
from ui_csa import CurrentSenseFrame
from ui_basic import OhmFrame, SeriesParallelFrame, LedFrame
from ui_firmware import TimerFrame, UartFrame, AdcFrame
from ui_power import RegFeedbackFrame, LdoFrame, BatteryFrame
from ui_filter import RcRlFrame, LcFrame, Timer555Frame

HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "circuit_calc.ico"

# 下拉選單項目（順序即顯示順序），以分隔線分組。
MODES = [
    ("分流電阻電流量測", CurrentSenseFrame),
    ("分壓電阻電壓", DividerFrame),
    ("單位換算器", UnitsFrame),
    ("歐姆定律 / 功率", OhmFrame),
    ("串 / 並聯電阻", SeriesParallelFrame),
    ("LED 限流電阻", LedFrame),
    ("STM32 Timer / PWM", TimerFrame),
    ("UART Baud 誤差", UartFrame),
    ("ADC 解析度", AdcFrame),
    ("穩壓器回授分壓", RegFeedbackFrame),
    ("LDO 功耗 / 發熱", LdoFrame),
    ("電池續航", BatteryFrame),
    ("RC / RL 濾波", RcRlFrame),
    ("LC 諧振", LcFrame),
    ("555 計時器", Timer555Frame),
]


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.frames: dict[str, tk.Frame] = {}
        self.current: tk.Frame | None = None
        self.mode_var = tk.StringVar()

        root.title("電路計算機")
        root.configure(bg=theme.BG)
        root.geometry("700x860")
        root.minsize(620, 700)
        try:
            root.iconbitmap(default=str(ICO_PATH))
        except Exception:
            pass

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # 上方：下拉選單切換計算項目
        bar = tk.Frame(root, bg=theme.BG)
        bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        tk.Label(bar, text="計算項目：", bg=theme.BG, fg=theme.TEXT_PRIMARY,
                 font=(theme.UI, 12, "bold")).pack(side="left")
        self.combo = ttk.Combobox(
            bar, textvariable=self.mode_var, values=[n for n, _ in MODES],
            state="readonly", width=24, font=(theme.UI, 12),
        )
        self.combo.pack(side="left", padx=(6, 0))
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.show(self.mode_var.get()))

        self.container = tk.Frame(root, bg=theme.BG)
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        root.bind("<Key>", self._on_key)

        self.show(MODES[0][0])
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
        self.mode_var.set(name)
        # 把焦點交給該分頁的第一個輸入框（若有），並延後再設一次避免被切換副作用搶走。
        target = getattr(frame, "focus_widget", None) or self.root
        target.focus_set()
        self.root.after_idle(target.focus_set)

    def _on_key(self, event: tk.Event) -> None:
        # Ctrl+1..9 快速跳到前九個項目（焦點在輸入框時也可用）
        if (event.state & 0x4) and event.keysym in "123456789":
            idx = int(event.keysym) - 1
            if 0 <= idx < len(MODES):
                self.show(MODES[idx][0])


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
