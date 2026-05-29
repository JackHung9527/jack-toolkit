"""共用 log 面板。

提供 .log(msg, level) 介面，level 可選 INFO / OK / WARN / ERR / TX / RX，
用顏色與標籤前綴區分。給 SCPI 命令收發紀錄與一般事件共用。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_LEVEL_COLORS = {
    "INFO": "#222222",
    "OK":   "#1a7f37",
    "WARN": "#bf8700",
    "ERR":  "#c00000",
    "TX":   "#0d4488",
    "RX":   "#5a3fb0",
}


class LogPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Log")
        self._text = tk.Text(
            self,
            height=10,
            wrap="none",
            font=("Consolas", 9),
            bg="#fafafa",
            state="disabled",
        )
        self._text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._text.yview)
        sb.pack(side="right", fill="y")
        self._text.configure(yscrollcommand=sb.set)

        for lvl, color in _LEVEL_COLORS.items():
            self._text.tag_configure(lvl, foreground=color)

    def log(self, msg: str, level: str = "INFO") -> None:
        level = level.upper() if level else "INFO"
        if level not in _LEVEL_COLORS:
            level = "INFO"
        line = f"[{level:>4}] {msg}\n"
        self._text.configure(state="normal")
        self._text.insert("end", line, level)
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
