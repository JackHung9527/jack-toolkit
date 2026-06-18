"""電路計算機共用樣式：淺色系配色、字型與小工具工廠。

與 tools/calculator/theme.py 同調，但只保留電路計算機會用到的子集，
並額外提供 bind_numpad_decimal_fix（修數字鍵盤小數點被 Tk 當成 Delete 的問題）。
"""

from __future__ import annotations

import tkinter as tk

# === 基本面板 ===
BG = "#e8e8e8"
PANEL = "#dde3ea"

# === 文字 ===
TEXT_PRIMARY = "#1b1b1b"
TEXT_SECONDARY = "#555555"
TEXT_MUTED = "#888888"
TEXT_ERROR = "#a3331f"
TEXT_OK = "#1b6b2f"

# === 輸入框 ===
ENTRY_BG = "#ffffff"
ENTRY_FG = "#1b1b1b"
SELECT_BG = "#ffffff"

# === 強調色 / 導覽 ===
ACCENT = "#005fb8"
NAV_FG = "#555555"
NAV_ACTIVE_BG = "#d2d8de"
NAV_ACTIVE_FG = "#003a6b"

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
    """修正數字鍵盤小數點問題。

    某些 NumLock / locale 狀態下，數字鍵盤的小數點鍵送進 Tk 時 keysym 會變成
    Delete / KP_Delete（char 仍是 '.'），於是 Entry 走內建刪除綁定、無法輸入小數點。
    這裡用前置綁定攔截：keysym 為 Delete/KP_Delete/KP_Decimal 且 char 是 '.'/','
    時，直接插入 '.' 並 break 掉刪除行為；真正的 Delete（char 為空）不受影響。
    """
    def handler(event: tk.Event):
        if event.keysym in ("KP_Decimal", "KP_Delete", "Delete") and event.char in (".", ","):
            try:
                entry.insert("insert", ".")
            except Exception:
                return None
            return "break"
        return None

    entry.bind("<KeyPress>", handler, add="+")


def make_entry(parent: tk.Widget, textvariable: tk.StringVar, width: int = 12) -> tk.Entry:
    """產生一個風格一致的數值輸入框（已套小數點修正）。"""
    ent = tk.Entry(
        parent, textvariable=textvariable, width=width,
        bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
        relief="flat", font=(MONO, 12), highlightthickness=1,
        highlightbackground=PANEL, highlightcolor=ACCENT,
    )
    bind_numpad_decimal_fix(ent)
    return ent


def make_result_text(parent: tk.Widget, height: int = 12) -> tk.Text:
    """產生唯讀結果顯示區。"""
    txt = tk.Text(
        parent, height=height, bg=ENTRY_BG, fg=TEXT_PRIMARY, relief="flat",
        font=(MONO, 11), wrap="word", padx=10, pady=8,
        highlightthickness=1, highlightbackground=PANEL,
    )
    txt.configure(state="disabled")
    return txt


def set_text(widget: tk.Text, content: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    widget.configure(state="disabled")


def title_label(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_PRIMARY, font=(UI, 16, "bold"))


def hint_label(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_SECONDARY,
                    font=(UI, 10), justify="left")
