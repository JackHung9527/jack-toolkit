"""共用 log widget。底部 status bar 與訊息區。"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk


class LogPanel(ttk.LabelFrame):
    """可滾動的訊息 log 區，支援不同等級顏色。"""

    LEVELS = {
        "INFO": "#1e1e1e",
        "OK":   "#117a2b",
        "WARN": "#a86700",
        "ERR":  "#c62828",
    }

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Log")
        self._text = tk.Text(self, height=10, wrap="none", state="disabled",
                             bg="#fafafa", fg="#1e1e1e", font=("Consolas", 9))
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._text.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        for tag, color in self.LEVELS.items():
            self._text.tag_configure(tag, foreground=color)

        btn_clear = ttk.Button(self, text="Clear", command=self.clear, width=8)
        btn_clear.grid(row=1, column=1, sticky="e", padx=2)

    def log(self, message: str, level: str = "INFO") -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        self._text.configure(state="normal")
        self._text.insert("end", line, level if level in self.LEVELS else "INFO")
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
