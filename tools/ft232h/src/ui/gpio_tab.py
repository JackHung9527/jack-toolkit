"""GPIO 分頁：16 個 pin，每個 pin 可設方向、讀寫值。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ..core.gpio_ctrl import GpioController, PIN_COUNT, PIN_NAMES
from ..core.device import default_url


class GpioTab(ttk.Frame):
    def __init__(self, master: tk.Misc, get_url: Callable[[], str], log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._get_url = get_url
        self._log = log
        self._ctrl = GpioController()
        self._poll_job: Optional[str] = None

        self._build()

    # ---------- 介面 ----------

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=6)

        ttk.Label(top, text="Frequency (Hz):").pack(side="left")
        self._freq_var = tk.StringVar(value="1000000")
        ttk.Entry(top, textvariable=self._freq_var, width=10).pack(side="left", padx=(4, 12))

        self._btn_open = ttk.Button(top, text="Open", command=self._on_open, width=8)
        self._btn_open.pack(side="left")
        self._btn_close = ttk.Button(top, text="Close", command=self._on_close, width=8, state="disabled")
        self._btn_close.pack(side="left", padx=4)

        self._poll_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Auto poll (200ms)", variable=self._poll_var,
                        command=self._on_poll_toggle).pack(side="left", padx=12)

        ttk.Button(top, text="Read once", command=self._on_read_once).pack(side="left")

        # pin 表
        grid = ttk.LabelFrame(self, text="Pins")
        grid.pack(side="top", fill="both", expand=False, padx=8, pady=4)

        headers = ["Pin", "Direction", "Output", "Read"]
        for col, name in enumerate(headers):
            ttk.Label(grid, text=name, font=("", 9, "bold")).grid(row=0, column=col, padx=8, pady=4, sticky="w")

        self._dir_vars: List[tk.StringVar] = []
        self._out_vars: List[tk.BooleanVar] = []
        self._read_labels: List[ttk.Label] = []

        for i in range(PIN_COUNT):
            ttk.Label(grid, text=PIN_NAMES[i]).grid(row=i + 1, column=0, sticky="w", padx=8)

            dvar = tk.StringVar(value="IN")
            combo = ttk.Combobox(grid, textvariable=dvar, values=["IN", "OUT"], width=5, state="readonly")
            combo.grid(row=i + 1, column=1, padx=4, pady=1)
            combo.bind("<<ComboboxSelected>>", lambda _e, idx=i: self._on_dir_change(idx))
            self._dir_vars.append(dvar)

            ovar = tk.BooleanVar(value=False)
            chk = ttk.Checkbutton(grid, text="HIGH", variable=ovar,
                                  command=lambda idx=i: self._on_out_change(idx))
            chk.grid(row=i + 1, column=2, padx=4)
            self._out_vars.append(ovar)

            lbl = ttk.Label(grid, text="-", width=5, anchor="center",
                            relief="sunken", background="#eeeeee")
            lbl.grid(row=i + 1, column=3, padx=4)
            self._read_labels.append(lbl)

        self._set_controls_enabled(False)

    # ---------- 動作 ----------

    def _on_open(self) -> None:
        url = self._get_url() or default_url()
        try:
            freq = int(self._freq_var.get())
        except ValueError:
            self._log("GPIO frequency invalid", "ERR")
            return
        try:
            self._ctrl.open(url, frequency_hz=freq)
        except Exception as ex:
            self._log(f"GPIO open failed: {ex}", "ERR")
            return
        self._log(f"GPIO opened @ {freq} Hz on {url}", "OK")
        self._btn_open.configure(state="disabled")
        self._btn_close.configure(state="normal")
        self._set_controls_enabled(True)

    def _on_close(self) -> None:
        self._stop_poll()
        self._ctrl.close()
        self._log("GPIO closed", "INFO")
        self._btn_open.configure(state="normal")
        self._btn_close.configure(state="disabled")
        self._set_controls_enabled(False)
        for lbl in self._read_labels:
            lbl.configure(text="-", background="#eeeeee")

    def _on_dir_change(self, pin: int) -> None:
        if not self._ctrl.is_open:
            return
        is_out = self._dir_vars[pin].get() == "OUT"
        try:
            self._ctrl.set_direction(pin, is_out)
            if is_out:
                # 套用目前 checkbox 狀態
                self._ctrl.write_pin(pin, self._out_vars[pin].get())
            self._log(f"{PIN_NAMES[pin]} -> {'OUT' if is_out else 'IN'}", "INFO")
        except Exception as ex:
            self._log(f"set_direction({PIN_NAMES[pin]}) failed: {ex}", "ERR")

    def _on_out_change(self, pin: int) -> None:
        if not self._ctrl.is_open:
            return
        if self._dir_vars[pin].get() != "OUT":
            self._log(f"{PIN_NAMES[pin]} is INPUT, output write ignored", "WARN")
            return
        try:
            self._ctrl.write_pin(pin, self._out_vars[pin].get())
        except Exception as ex:
            self._log(f"write_pin({PIN_NAMES[pin]}) failed: {ex}", "ERR")

    def _on_read_once(self) -> None:
        if not self._ctrl.is_open:
            return
        self._refresh_read()

    def _on_poll_toggle(self) -> None:
        if self._poll_var.get():
            self._start_poll()
        else:
            self._stop_poll()

    def _start_poll(self) -> None:
        if self._poll_job is not None:
            return
        self._poll_tick()

    def _stop_poll(self) -> None:
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def _poll_tick(self) -> None:
        if not self._ctrl.is_open or not self._poll_var.get():
            self._poll_job = None
            return
        self._refresh_read()
        self._poll_job = self.after(200, self._poll_tick)

    def _refresh_read(self) -> None:
        try:
            word = self._ctrl.read_all()
        except Exception as ex:
            self._log(f"GPIO read failed: {ex}", "ERR")
            return
        for i in range(PIN_COUNT):
            level = (word >> i) & 0x1
            self._read_labels[i].configure(
                text="1" if level else "0",
                background="#c8e6c9" if level else "#ffcdd2",
            )

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        # 16 pin combobox + checkbutton 都要鎖
        for child in self.winfo_children():
            self._walk_set_state(child, enabled)
        # 但 Open/Close 自己管
        self._btn_open.configure(state="disabled" if enabled else "normal")
        self._btn_close.configure(state="normal" if enabled else "disabled")

    def _walk_set_state(self, widget: tk.Misc, enabled: bool) -> None:
        if isinstance(widget, ttk.Combobox):
            widget.configure(state="readonly" if enabled else "disabled")
        elif isinstance(widget, (ttk.Checkbutton, ttk.Button)):
            # 不動 Open / Close / Read once / Auto poll 按鈕本身（最外層 top frame 已單獨處理）
            pass
        for ch in widget.winfo_children():
            self._walk_set_state(ch, enabled)

    def on_app_close(self) -> None:
        self._stop_poll()
        self._ctrl.close()
