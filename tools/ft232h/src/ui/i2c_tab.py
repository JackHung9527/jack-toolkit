"""I2C 分頁：scan、register read/write、raw read/write。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from common.hex_utils import format_hex, parse_hex

from ..core.device import default_url
from ..core.i2c_ctrl import DEFAULT_FREQUENCY, I2cCtrl


class I2cTab(ttk.Frame):
    def __init__(self, master: tk.Misc, get_url: Callable[[], str], log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._get_url = get_url
        self._log = log
        self._ctrl = I2cCtrl()
        self._build()

    def _build(self) -> None:
        # ---- 連線參數 ----
        cfg = ttk.LabelFrame(self, text="Config")
        cfg.pack(side="top", fill="x", padx=8, pady=6)

        ttk.Label(cfg, text="Frequency:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._freq_var = tk.StringVar(value=str(DEFAULT_FREQUENCY))
        ttk.Combobox(cfg, textvariable=self._freq_var, width=12, state="readonly",
                     values=["100000", "400000", "1000000"]).grid(row=0, column=1, sticky="w")

        self._btn_open = ttk.Button(cfg, text="Open", command=self._on_open, width=8)
        self._btn_open.grid(row=0, column=2, padx=8)
        self._btn_close = ttk.Button(cfg, text="Close", command=self._on_close, width=8, state="disabled")
        self._btn_close.grid(row=0, column=3)
        self._btn_scan = ttk.Button(cfg, text="Scan bus", command=self._on_scan, width=10, state="disabled")
        self._btn_scan.grid(row=0, column=4, padx=8)

        ttk.Label(cfg, text="Pinout: AD0=SCL  AD1+AD2=SDA  (需外接 4.7k pull-up 到 VCC)",
                  foreground="#666").grid(row=1, column=0, columnspan=5, sticky="w", padx=4, pady=(2, 4))

        # ---- 操作 ----
        op = ttk.LabelFrame(self, text="Transfer")
        op.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        ttk.Label(op, text="Slave Addr (7-bit hex):").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._addr_var = tk.StringVar(value="0x50")
        ttk.Entry(op, textvariable=self._addr_var, width=8).grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(op, text="Reg (hex):").grid(row=0, column=2, sticky="e", padx=4)
        self._reg_var = tk.StringVar(value="0x00")
        ttk.Entry(op, textvariable=self._reg_var, width=8).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(op, text="Length:").grid(row=0, column=4, sticky="e", padx=4)
        self._len_var = tk.StringVar(value="1")
        ttk.Entry(op, textvariable=self._len_var, width=6).grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(op, text="Data (hex):").grid(row=1, column=0, sticky="ne", padx=4, pady=4)
        self._data_text = tk.Text(op, height=3, width=60, font=("Consolas", 10))
        self._data_text.grid(row=1, column=1, columnspan=5, sticky="ew", padx=4)
        self._data_text.insert("1.0", "")

        btns = ttk.Frame(op)
        btns.grid(row=2, column=1, columnspan=5, sticky="w", padx=4, pady=4)
        self._btn_rd_reg = ttk.Button(btns, text="Read Reg", command=self._on_read_reg, state="disabled", width=12)
        self._btn_rd_reg.pack(side="left", padx=2)
        self._btn_wr_reg = ttk.Button(btns, text="Write Reg", command=self._on_write_reg, state="disabled", width=12)
        self._btn_wr_reg.pack(side="left", padx=2)
        self._btn_rd = ttk.Button(btns, text="Raw Read", command=self._on_raw_read, state="disabled", width=12)
        self._btn_rd.pack(side="left", padx=2)
        self._btn_wr = ttk.Button(btns, text="Raw Write", command=self._on_raw_write, state="disabled", width=12)
        self._btn_wr.pack(side="left", padx=2)

        ttk.Label(op, text="RX (hex):").grid(row=3, column=0, sticky="ne", padx=4, pady=4)
        self._rx_text = tk.Text(op, height=6, width=60, state="disabled", font=("Consolas", 10),
                                bg="#fafafa")
        self._rx_text.grid(row=3, column=1, columnspan=5, sticky="nsew", padx=4, pady=4)

        op.columnconfigure(5, weight=1)
        op.rowconfigure(3, weight=1)

    # ---------- 動作 ----------

    def _on_open(self) -> None:
        url = self._get_url() or default_url()
        try:
            freq = int(self._freq_var.get())
        except ValueError:
            self._log("I2C frequency invalid", "ERR")
            return
        try:
            self._ctrl.open(url, frequency_hz=freq)
        except Exception as ex:
            self._log(f"I2C open failed: {ex}", "ERR")
            return
        self._log(f"I2C opened @ {freq} Hz", "OK")
        self._btn_open.configure(state="disabled")
        self._btn_close.configure(state="normal")
        for b in (self._btn_scan, self._btn_rd_reg, self._btn_wr_reg, self._btn_rd, self._btn_wr):
            b.configure(state="normal")

    def _on_close(self) -> None:
        self._ctrl.close()
        self._log("I2C closed", "INFO")
        self._btn_open.configure(state="normal")
        self._btn_close.configure(state="disabled")
        for b in (self._btn_scan, self._btn_rd_reg, self._btn_wr_reg, self._btn_rd, self._btn_wr):
            b.configure(state="disabled")

    def _on_scan(self) -> None:
        try:
            found = self._ctrl.scan()
        except Exception as ex:
            self._log(f"I2C scan failed: {ex}", "ERR")
            return
        if not found:
            self._log("I2C scan: no device found (檢查 pull-up / 接線)", "WARN")
            self._show_rx(b"")
            return
        text = " ".join(f"0x{a:02X}" for a in found)
        self._log(f"I2C scan found {len(found)} device(s): {text}", "OK")
        self._rx_text.configure(state="normal")
        self._rx_text.delete("1.0", "end")
        self._rx_text.insert("end", text)
        self._rx_text.configure(state="disabled")

    def _parse_addr(self) -> int:
        return int(self._addr_var.get(), 0) & 0x7F

    def _parse_reg(self) -> int:
        return int(self._reg_var.get(), 0) & 0xFF

    def _parse_len(self) -> int:
        return int(self._len_var.get(), 0)

    def _on_read_reg(self) -> None:
        try:
            addr = self._parse_addr()
            reg = self._parse_reg()
            length = self._parse_len()
        except ValueError:
            self._log("addr / reg / length invalid", "ERR")
            return
        try:
            data = self._ctrl.read_reg(addr, reg, length)
        except Exception as ex:
            self._log(f"I2C read_reg failed: {ex}", "ERR")
            return
        self._show_rx(data)
        self._log(f"I2C 0x{addr:02X} reg 0x{reg:02X} read {length}: {format_hex(data)}", "OK")

    def _on_write_reg(self) -> None:
        try:
            addr = self._parse_addr()
            reg = self._parse_reg()
            data = parse_hex(self._data_text.get("1.0", "end"))
        except Exception as ex:
            self._log(f"input parse: {ex}", "ERR")
            return
        try:
            self._ctrl.write_reg(addr, reg, data)
            self._log(f"I2C 0x{addr:02X} reg 0x{reg:02X} write: {format_hex(data)}", "OK")
        except Exception as ex:
            self._log(f"I2C write_reg failed: {ex}", "ERR")

    def _on_raw_read(self) -> None:
        try:
            addr = self._parse_addr()
            length = self._parse_len()
        except ValueError:
            self._log("addr / length invalid", "ERR")
            return
        try:
            data = self._ctrl.read(addr, length)
        except Exception as ex:
            self._log(f"I2C read failed: {ex}", "ERR")
            return
        self._show_rx(data)
        self._log(f"I2C 0x{addr:02X} raw read {length}: {format_hex(data)}", "OK")

    def _on_raw_write(self) -> None:
        try:
            addr = self._parse_addr()
            data = parse_hex(self._data_text.get("1.0", "end"))
        except Exception as ex:
            self._log(f"input parse: {ex}", "ERR")
            return
        try:
            self._ctrl.write(addr, data)
            self._log(f"I2C 0x{addr:02X} raw write: {format_hex(data)}", "OK")
        except Exception as ex:
            self._log(f"I2C write failed: {ex}", "ERR")

    def _show_rx(self, data: bytes) -> None:
        self._rx_text.configure(state="normal")
        self._rx_text.delete("1.0", "end")
        self._rx_text.insert("end", format_hex(data, group=8))
        self._rx_text.configure(state="disabled")

    def on_app_close(self) -> None:
        self._ctrl.close()
