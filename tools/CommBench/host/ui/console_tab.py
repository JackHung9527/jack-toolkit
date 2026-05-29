"""Raw SCPI console — 直接打 SCPI 命令、看原始回應。

給快速試 HELP? / *IDN? / 韌體新增但 UI 還沒做的命令用。
有輸入歷史（↑/↓）。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..core.scpi_client import ScpiClient, ScpiError


HISTORY_MAX = 50


class ConsoleTab(ttk.Frame):
    def __init__(self, master: tk.Misc, client: ScpiClient,
                 log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._client = client
        self._log = log
        self._history: list[str] = []
        self._hist_idx: int = -1
        self._busy = False
        self._build()
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        self._send_btn.configure(state=state)
        self._idn_btn.configure(state=state)
        self._help_btn.configure(state=state)
        self._led_on_btn.configure(state=state)
        self._led_off_btn.configure(state=state)
        self._entry.configure(state=state if connected else "disabled")

    def _build(self) -> None:
        # 命令輸入
        top = ttk.LabelFrame(self, text="SCPI command")
        top.pack(side="top", fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text=">").grid(row=0, column=0, sticky="e", padx=(6, 2))
        self._cmd_var = tk.StringVar()
        self._entry = ttk.Entry(top, textvariable=self._cmd_var, font=("Consolas", 10))
        self._entry.grid(row=0, column=1, sticky="ew", padx=2, pady=6)
        self._entry.bind("<Return>", lambda _e: self._on_send())
        self._entry.bind("<Up>",     lambda _e: self._hist_prev())
        self._entry.bind("<Down>",   lambda _e: self._hist_next())

        self._send_btn = ttk.Button(top, text="Send", width=8, command=self._on_send)
        self._send_btn.grid(row=0, column=2, padx=(2, 6))

        # 快捷命令
        quick = ttk.Frame(top)
        quick.grid(row=1, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))
        ttk.Label(quick, text="快捷:", foreground="#666").pack(side="left", padx=(2, 4))
        self._idn_btn = ttk.Button(quick, text="*IDN?", width=8,
                                   command=lambda: self._send_cmd("*IDN?"))
        self._idn_btn.pack(side="left", padx=2)
        self._help_btn = ttk.Button(quick, text="HELP?", width=8,
                                    command=lambda: self._send_cmd("HELP?"))
        self._help_btn.pack(side="left", padx=2)
        self._led_on_btn = ttk.Button(quick, text="LED:ON", width=8,
                                      command=lambda: self._send_cmd("LED:ON"))
        self._led_on_btn.pack(side="left", padx=2)
        self._led_off_btn = ttk.Button(quick, text="LED:OFF", width=8,
                                       command=lambda: self._send_cmd("LED:OFF"))
        self._led_off_btn.pack(side="left", padx=2)

        top.columnconfigure(1, weight=1)

        # 回應顯示
        out = ttk.LabelFrame(self, text="Response")
        out.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        self._out_text = tk.Text(out, font=("Consolas", 10), bg="#fafafa",
                                 state="disabled", wrap="none")
        self._out_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(out, orient="vertical", command=self._out_text.yview)
        sb.pack(side="right", fill="y")
        self._out_text.configure(yscrollcommand=sb.set)

        self._out_text.tag_configure("TX", foreground="#0d4488")
        self._out_text.tag_configure("RX", foreground="#222222")
        self._out_text.tag_configure("ERR", foreground="#c00000")

    # ----------------- internal -----------------

    def _append(self, msg: str, tag: str) -> None:
        self._out_text.configure(state="normal")
        self._out_text.insert("end", msg + "\n", tag)
        self._out_text.see("end")
        self._out_text.configure(state="disabled")

    def _on_send(self) -> None:
        cmd = self._cmd_var.get().strip()
        if not cmd:
            return
        if self._busy:
            self._log("命令進行中，請稍候", "WARN")
            return
        self._cmd_var.set("")
        self._push_history(cmd)
        self._send_cmd(cmd)

    def _send_cmd(self, cmd: str) -> None:
        if self._busy:
            self._log("命令進行中，請稍候", "WARN")
            return
        self._busy = True
        self._append(f"> {cmd}", "TX")
        self._log(cmd, "TX")

        def _worker():
            try:
                try:
                    lines = self._client.query(cmd)
                except ScpiError as exc:
                    msg = str(exc)
                    self.after(0, lambda: self._append(f"  ERR: {msg}", "ERR"))
                    self._log(msg, "ERR")
                    return
                if not lines:
                    self.after(0, lambda: self._append("  (no response)", "ERR"))
                    self._log("(no response)", "WARN")
                    return
                for ln in lines:
                    self.after(0, lambda l=ln: self._append(f"  {l}", "RX"))
                self._log(f"{len(lines)} line(s) RX", "RX")
            finally:
                self._busy = False

        threading.Thread(target=_worker, daemon=True).start()

    def _push_history(self, cmd: str) -> None:
        # 跟最後一筆相同就不重複加
        if self._history and self._history[-1] == cmd:
            self._hist_idx = len(self._history)
            return
        self._history.append(cmd)
        if len(self._history) > HISTORY_MAX:
            self._history = self._history[-HISTORY_MAX:]
        self._hist_idx = len(self._history)

    def _hist_prev(self) -> None:
        if not self._history:
            return
        if self._hist_idx > 0:
            self._hist_idx -= 1
        self._cmd_var.set(self._history[self._hist_idx])
        self._entry.icursor("end")

    def _hist_next(self) -> None:
        if not self._history:
            return
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            self._cmd_var.set(self._history[self._hist_idx])
        else:
            self._hist_idx = len(self._history)
            self._cmd_var.set("")
        self._entry.icursor("end")
