"""SPI 分頁：可選 CS / mode / freq，做 write、read、exchange。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..core.spi_ctrl import SpiCtrl, CS_LINE_COUNT, DEFAULT_FREQUENCY
from ..core.device import default_url
from .hexutil import parse_hex, format_hex


class SpiTab(ttk.Frame):
    def __init__(self, master: tk.Misc, get_url: Callable[[], str], log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._get_url = get_url
        self._log = log
        self._ctrl = SpiCtrl()
        self._build()

    def _build(self) -> None:
        # ---- 連線參數 ----
        cfg = ttk.LabelFrame(self, text="Config")
        cfg.pack(side="top", fill="x", padx=8, pady=6)

        ttk.Label(cfg, text="CS:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._cs_var = tk.IntVar(value=0)
        ttk.Combobox(cfg, textvariable=self._cs_var, width=4, state="readonly",
                     values=list(range(CS_LINE_COUNT))).grid(row=0, column=1, sticky="w")

        ttk.Label(cfg, text="Frequency (Hz):").grid(row=0, column=2, sticky="e", padx=4)
        self._freq_var = tk.StringVar(value=str(DEFAULT_FREQUENCY))
        ttk.Entry(cfg, textvariable=self._freq_var, width=12).grid(row=0, column=3, sticky="w")

        ttk.Label(cfg, text="Mode:").grid(row=0, column=4, sticky="e", padx=4)
        self._mode_var = tk.IntVar(value=0)
        ttk.Combobox(cfg, textvariable=self._mode_var, width=4, state="readonly",
                     values=[0, 1, 2, 3]).grid(row=0, column=5, sticky="w")

        self._btn_open = ttk.Button(cfg, text="Open", command=self._on_open, width=8)
        self._btn_open.grid(row=0, column=6, padx=8)
        self._btn_close = ttk.Button(cfg, text="Close", command=self._on_close, width=8, state="disabled")
        self._btn_close.grid(row=0, column=7)

        ttk.Label(cfg, text="Pinout: AD0=SCK  AD1=MOSI  AD2=MISO  AD3..AD7=CS0..CS4",
                  foreground="#666").grid(row=1, column=0, columnspan=8, sticky="w", padx=4, pady=(2, 4))

        # ---- 傳輸區 ----
        tx = ttk.LabelFrame(self, text="Transfer")
        tx.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        ttk.Label(tx, text="TX (hex):").grid(row=0, column=0, sticky="ne", padx=4, pady=4)
        self._tx_text = tk.Text(tx, height=4, width=60, font=("Consolas", 10))
        self._tx_text.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self._tx_text.insert("1.0", "DE AD BE EF")

        ttk.Label(tx, text="RX length:").grid(row=1, column=0, sticky="e", padx=4)
        self._rx_len_var = tk.StringVar(value="4")
        ttk.Entry(tx, textvariable=self._rx_len_var, width=8).grid(row=1, column=1, sticky="w", padx=4)

        self._duplex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tx, text="Full duplex (exchange)", variable=self._duplex_var).grid(
            row=1, column=1, sticky="e", padx=4)

        btns = ttk.Frame(tx)
        btns.grid(row=2, column=1, sticky="w", padx=4, pady=4)
        self._btn_write = ttk.Button(btns, text="Write", command=self._on_write, state="disabled", width=10)
        self._btn_write.pack(side="left", padx=2)
        self._btn_read = ttk.Button(btns, text="Read", command=self._on_read, state="disabled", width=10)
        self._btn_read.pack(side="left", padx=2)
        self._btn_xchg = ttk.Button(btns, text="Exchange", command=self._on_exchange, state="disabled", width=10)
        self._btn_xchg.pack(side="left", padx=2)

        ttk.Label(tx, text="RX (hex):").grid(row=3, column=0, sticky="ne", padx=4)
        self._rx_text = tk.Text(tx, height=6, width=60, state="disabled", font=("Consolas", 10),
                                bg="#fafafa")
        self._rx_text.grid(row=3, column=1, sticky="nsew", padx=4, pady=4)

        tx.columnconfigure(1, weight=1)
        tx.rowconfigure(3, weight=1)

    # ---------- 動作 ----------

    def _on_open(self) -> None:
        url = self._get_url() or default_url()
        try:
            freq = int(self._freq_var.get())
            cs = int(self._cs_var.get())
            mode = int(self._mode_var.get())
        except ValueError:
            self._log("SPI config invalid", "ERR")
            return
        try:
            self._ctrl.open(url, cs=cs, frequency_hz=freq, mode=mode)
        except Exception as ex:
            self._log(f"SPI open failed: {ex}", "ERR")
            return
        self._log(f"SPI opened CS{cs} mode{mode} @ {freq} Hz", "OK")
        self._btn_open.configure(state="disabled")
        self._btn_close.configure(state="normal")
        for b in (self._btn_write, self._btn_read, self._btn_xchg):
            b.configure(state="normal")

    def _on_close(self) -> None:
        self._ctrl.close()
        self._log("SPI closed", "INFO")
        self._btn_open.configure(state="normal")
        self._btn_close.configure(state="disabled")
        for b in (self._btn_write, self._btn_read, self._btn_xchg):
            b.configure(state="disabled")

    def _on_write(self) -> None:
        try:
            data = parse_hex(self._tx_text.get("1.0", "end"))
        except Exception as ex:
            self._log(f"TX hex parse: {ex}", "ERR")
            return
        try:
            self._ctrl.write(data)
            self._log(f"SPI write {len(data)} byte(s): {format_hex(data)}", "OK")
        except Exception as ex:
            self._log(f"SPI write failed: {ex}", "ERR")

    def _on_read(self) -> None:
        try:
            length = int(self._rx_len_var.get())
        except ValueError:
            self._log("RX length invalid", "ERR")
            return
        try:
            data = self._ctrl.read(length)
        except Exception as ex:
            self._log(f"SPI read failed: {ex}", "ERR")
            return
        self._show_rx(data)
        self._log(f"SPI read {len(data)} byte(s)", "OK")

    def _on_exchange(self) -> None:
        try:
            tx = parse_hex(self._tx_text.get("1.0", "end"))
        except Exception as ex:
            self._log(f"TX hex parse: {ex}", "ERR")
            return
        try:
            rx_len = int(self._rx_len_var.get())
        except ValueError:
            self._log("RX length invalid", "ERR")
            return
        duplex = self._duplex_var.get()
        try:
            rx = self._ctrl.exchange(tx, rx_len, duplex=duplex)
        except Exception as ex:
            self._log(f"SPI exchange failed: {ex}", "ERR")
            return
        self._show_rx(rx)
        mode_txt = "duplex" if duplex else "half-duplex"
        self._log(f"SPI exchange ({mode_txt}) TX {len(tx)} -> RX {len(rx)}", "OK")

    def _show_rx(self, data: bytes) -> None:
        self._rx_text.configure(state="normal")
        self._rx_text.delete("1.0", "end")
        self._rx_text.insert("end", format_hex(data, group=8))
        self._rx_text.configure(state="disabled")

    def on_app_close(self) -> None:
        self._ctrl.close()
