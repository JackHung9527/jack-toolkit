"""小算盤共用樣式：淺色系配色與按鈕工廠。"""

from __future__ import annotations

import tkinter as tk

# === 基本面板 ===
BG = "#e8e8e8"            # 視窗 / 按鈕間隙
PANEL = "#dde3ea"        # 面板（進位表、結果區）
DISPLAY_BG = "#e8e8e8"

# === 文字 ===
EXPR_FG = "#6a6a6a"
RESULT_FG = "#1b1b1b"
TEXT_PRIMARY = "#1b1b1b"
TEXT_SECONDARY = "#555555"
TEXT_MUTED = "#888888"

# === 輸入框 ===
ENTRY_BG = "#ffffff"
ENTRY_FG = "#1b1b1b"
SELECT_BG = "#ffffff"    # radiobutton 勾選指示底色

# === 強調色 ===
ACCENT = "#005fb8"

# === 按鈕 ===
NUM_BG = "#fcfcfc"
NUM_HOVER = "#eef1f4"
FN_BG = "#ededed"
FN_HOVER = "#e0e4e8"
FN_FG = "#1b1b1b"
MEM_FG = "#555555"
EQ_BG = "#005fb8"
EQ_HOVER = "#1a76c8"
EQ_FG = "#ffffff"
ANGLE_FG = "#b35900"

# === 切換 / 導覽高亮 ===
TOGGLE_ON_BG = "#005fb8"
TOGGLE_ON_FG = "#ffffff"
TOGGLE_OFF_FG = "#555555"
NAV_FG = "#555555"
NAV_ACTIVE_BG = "#d2d8de"
NAV_ACTIVE_FG = "#003a6b"
DISABLED_FG = "#b3b3b3"

MONO = "Consolas"
UI = "Segoe UI"

_KIND = {
    "num": (NUM_BG, NUM_HOVER, TEXT_PRIMARY),
    "op": (FN_BG, FN_HOVER, FN_FG),
    "fn": (FN_BG, FN_HOVER, FN_FG),
    "eq": (EQ_BG, EQ_HOVER, EQ_FG),
}


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

    在某些 NumLock / locale 狀態下，數字鍵盤的小數點鍵送進 Tk 時 keysym 會變成
    Delete / KP_Delete（char 仍是 '.'），於是 Entry 走內建刪除綁定、無法輸入小數點。
    這裡用前置綁定攔截：keysym 為 Delete/KP_Delete/KP_Decimal 且 char 是 '.'/',' 時，
    直接插入 '.' 並 break 掉刪除行為；真正的 Delete（char 為空）不受影響。
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


def grid_button(parent: tk.Widget, text: str, r: int, c: int, cmd, kind: str = "num",
                rowspan: int = 1, colspan: int = 1, font=None, padx: int = 2, pady: int = 2) -> tk.Button:
    bg, hover, fg = _KIND.get(kind, _KIND["num"])
    if font is None:
        font = (UI, 16) if kind == "num" else (UI, 13)
    b = tk.Button(
        parent, text=text, command=cmd, bg=bg, fg=fg,
        activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, font=font, cursor="hand2",
        disabledforeground=DISABLED_FG, takefocus=0,
    )
    b.grid(row=r, column=c, rowspan=rowspan, columnspan=colspan,
           sticky="nsew", padx=padx, pady=pady)
    add_hover(b, bg, hover)
    return b
