"""校正設計工具共用樣式（自含，不依賴其他工具）。

配色與 jack-toolkit 其他工具同調的淺色系，並附 bind_numpad_decimal_fix
（修數字鍵盤小數點在某些 NumLock/locale 下被 Tk 當成 Delete 的問題）。
"""

from __future__ import annotations

import tkinter as tk

# === 基本面板 ===
BG = "#e8e8e8"
PANEL = "#dde3ea"
GROUP_BG = "#f2f4f7"

# === 文字 ===
TEXT_PRIMARY = "#1b1b1b"
TEXT_SECONDARY = "#555555"
TEXT_MUTED = "#888888"
TEXT_ERROR = "#a3331f"
TEXT_OK = "#1b6b2f"

# === 輸入框 ===
ENTRY_BG = "#ffffff"
ENTRY_FG = "#1b1b1b"

# === 強調色 ===
ACCENT = "#005fb8"
ACCENT_HOVER = "#1f74c8"

# === 圖表顏色（matplotlib 也共用） ===
PLOT_RAW = "#888888"        # 原始散點
PLOT_OPT = "#005fb8"        # 最佳化折線
PLOT_UNIFORM = "#d08a1f"    # 均勻折線
PLOT_TARGET = "#a3331f"     # 目標誤差線

MONO = "Consolas"
UI = "Segoe UI"


def add_hover(btn: tk.Button, base: str, hover: str) -> None:
    def on_enter(_e: tk.Event) -> None:
        if str(btn["state"]) != "disabled":
            btn.configure(bg=hover)

    def on_leave(_e: tk.Event) -> None:
        btn.configure(bg=base)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)


def bind_numpad_decimal_fix(entry: tk.Entry) -> None:
    """修正數字鍵盤小數點在某些狀態下被當 Delete、打不進去的問題。"""
    def handler(event: tk.Event):
        if event.keysym in ("KP_Decimal", "KP_Delete", "Delete") and event.char in (".", ","):
            try:
                entry.insert("insert", ".")
            except Exception:
                return None
            return "break"
        return None

    entry.bind("<KeyPress>", handler, add="+")


def make_entry(parent: tk.Widget, textvariable: tk.StringVar, width: int = 10) -> tk.Entry:
    ent = tk.Entry(
        parent, textvariable=textvariable, width=width,
        bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
        relief="flat", font=(MONO, 12), highlightthickness=1,
        highlightbackground=PANEL, highlightcolor=ACCENT,
    )
    bind_numpad_decimal_fix(ent)
    return ent


def make_button(parent: tk.Widget, text: str, command, width: int = 0) -> tk.Button:
    btn = tk.Button(
        parent, text=text, command=command, relief="flat",
        bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER,
        activeforeground="#ffffff", font=(UI, 10, "bold"),
        cursor="hand2", padx=8, pady=4, bd=0,
    )
    if width:
        btn.configure(width=width)
    add_hover(btn, ACCENT, ACCENT_HOVER)
    return btn


def group(parent: tk.Widget, title: str) -> tk.LabelFrame:
    return tk.LabelFrame(
        parent, text=title, bg=BG, fg=TEXT_SECONDARY,
        font=(UI, 10, "bold"), padx=8, pady=6, relief="groove", bd=1,
    )
