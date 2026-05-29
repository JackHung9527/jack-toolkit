"""I2C 操作分頁 — scan / probe / read / write / mem read / mem write。

所有操作都走 ScpiClient 同步呼叫，並把 TX/RX 寫到 log panel。
為避免 I2C 操作（最壞 ~100ms）阻塞 Tk event loop，每個按鈕都丟到背景執行緒。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from common.hex_utils import format_hex, parse_hex

from ..core.scpi_client import ScpiClient, ScpiError


class I2cTab(ttk.Frame):
    def __init__(self, master: tk.Misc, client: ScpiClient,
                 log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._client = client
        self._log = log
        self._busy = False
        self._build()
        self.set_connected(False)

    # ---------------- public ----------------

    def set_connected(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        for btn in (self._btn_probe, self._btn_scan,
                    self._btn_read, self._btn_write,
                    self._btn_mread, self._btn_mwrite,
                    self._btn_recover):
            btn.configure(state=state)
        if not connected:
            self._bus_idle_var.set("bus: ?")
            self._bus_idle_label.configure(foreground="#666")

    # ---------------- build ----------------

    def _build(self) -> None:
        # === Bus row ===
        top = ttk.LabelFrame(self, text="Bus  (G071 I2C1 — PB8/SCL  PB9/SDA  @ 100 kHz)")
        top.pack(side="top", fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text="Slave addr (7-bit):").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._addr_var = tk.StringVar(value="0x50")
        ttk.Entry(top, textvariable=self._addr_var, width=8,
                  font=("Consolas", 10)).grid(row=0, column=1, sticky="w", padx=4)

        self._btn_probe = ttk.Button(top, text="Probe (ACK?)", width=14, command=self._on_probe)
        self._btn_probe.grid(row=0, column=2, padx=4)
        self._btn_scan = ttk.Button(top, text="Scan 0x08-0x77", width=16, command=self._on_scan)
        self._btn_scan.grid(row=0, column=3, padx=4)

        # bus recovery + idle 指示
        self._btn_recover = ttk.Button(top, text="Recover bus", width=12,
                                       command=self._on_recover)
        self._btn_recover.grid(row=0, column=4, padx=(12, 4))
        self._bus_idle_var = tk.StringVar(value="bus: ?")
        self._bus_idle_label = ttk.Label(top, textvariable=self._bus_idle_var,
                                         font=("Consolas", 9, "bold"), foreground="#666")
        self._bus_idle_label.grid(row=0, column=5, padx=4)
        ttk.Button(top, text="Check", width=7,
                   command=self._on_check_bus).grid(row=0, column=6, padx=4)

        # Scan 結果 grid
        scan_box = ttk.LabelFrame(self, text="Scan 結果")
        scan_box.pack(side="top", fill="x", padx=8, pady=4)
        self._scan_text = tk.Text(scan_box, height=4, font=("Consolas", 10),
                                  bg="#fafafa", state="disabled")
        self._scan_text.pack(side="top", fill="x", padx=4, pady=4)

        # === Transfer row (raw / mem 二選一) ===
        op = ttk.LabelFrame(self, text="Transfer")
        op.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        ttk.Label(op, text="Register (hex):").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._reg_var = tk.StringVar(value="0x00")
        ttk.Entry(op, textvariable=self._reg_var, width=8,
                  font=("Consolas", 10)).grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(op, text="Length:").grid(row=0, column=2, sticky="e", padx=4)
        self._len_var = tk.StringVar(value="1")
        ttk.Entry(op, textvariable=self._len_var, width=6).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(op, text="(最大 64 bytes)", foreground="#888").grid(
            row=0, column=4, sticky="w", padx=4)

        ttk.Label(op, text="TX data (hex):").grid(row=1, column=0, sticky="ne", padx=4, pady=4)
        self._tx_text = tk.Text(op, height=3, width=58, font=("Consolas", 10))
        self._tx_text.grid(row=1, column=1, columnspan=4, sticky="ew", padx=4)

        btns = ttk.Frame(op)
        btns.grid(row=2, column=1, columnspan=4, sticky="w", padx=4, pady=4)
        self._btn_read = ttk.Button(btns, text="Raw Read", width=12, command=self._on_raw_read)
        self._btn_read.pack(side="left", padx=2)
        self._btn_write = ttk.Button(btns, text="Raw Write", width=12, command=self._on_raw_write)
        self._btn_write.pack(side="left", padx=2)
        self._btn_mread = ttk.Button(btns, text="Mem Read (reg)", width=16, command=self._on_mem_read)
        self._btn_mread.pack(side="left", padx=2)
        self._btn_mwrite = ttk.Button(btns, text="Mem Write (reg)", width=16, command=self._on_mem_write)
        self._btn_mwrite.pack(side="left", padx=2)

        ttk.Label(op, text="RX data (hex):").grid(row=3, column=0, sticky="ne", padx=4, pady=4)
        self._rx_text = tk.Text(op, height=6, width=58, font=("Consolas", 10),
                                bg="#fafafa", state="disabled")
        self._rx_text.grid(row=3, column=1, columnspan=4, sticky="nsew", padx=4)
        op.columnconfigure(4, weight=1)
        op.rowconfigure(3, weight=1)

    # ---------------- helpers ----------------

    def _parse_u8(self, s: str, what: str) -> int:
        s = s.strip()
        try:
            v = int(s, 0)
        except ValueError:
            raise ValueError(f"{what} 不是合法數字: {s!r}")
        if not (0 <= v <= 0xFF):
            raise ValueError(f"{what} 超出 0x00-0xFF 範圍")
        return v

    def _parse_len(self, s: str) -> int:
        s = s.strip()
        try:
            v = int(s, 0)
        except ValueError:
            raise ValueError(f"length 不是合法數字: {s!r}")
        if not (1 <= v <= 64):
            raise ValueError("length 必須在 1~64 之間")
        return v

    def _set_rx(self, data: bytes) -> None:
        self._rx_text.configure(state="normal")
        self._rx_text.delete("1.0", "end")
        if data:
            self._rx_text.insert("1.0", format_hex(data))
        self._rx_text.configure(state="disabled")

    def _set_scan_result(self, addrs: list[int]) -> None:
        self._scan_text.configure(state="normal")
        self._scan_text.delete("1.0", "end")
        if not addrs:
            self._scan_text.insert("1.0", "(沒掃到任何 device — 檢查 pull-up 與 wiring)")
        else:
            txt = f"找到 {len(addrs)} 個 device:\n  " + "  ".join(f"0x{a:02X}" for a in addrs)
            self._scan_text.insert("1.0", txt)
        self._scan_text.configure(state="disabled")

    def _run_bg(self, fn) -> None:
        """把長操作丟到背景跑，避免阻塞 UI；同時間只允許一個。"""
        if self._busy:
            self._log("操作進行中，請稍候", "WARN")
            return
        self._busy = True

        def _worker():
            try:
                fn()
            finally:
                self._busy = False

        threading.Thread(target=_worker, daemon=True).start()

    # ---------------- handlers ----------------

    def _on_probe(self) -> None:
        try:
            addr = self._parse_u8(self._addr_var.get(), "addr")
        except ValueError as exc:
            self._log(str(exc), "ERR")
            return

        def do():
            cmd = f"I2C1:PROBE 0x{addr:02X}"
            self._log(cmd, "TX")
            try:
                ack = self._client.i2c_probe(addr)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"{'ACK' if ack else 'NACK'} @ 0x{addr:02X}", "OK" if ack else "WARN")

        self._run_bg(do)

    def _on_scan(self) -> None:
        def do():
            cmd = "I2C1:SCAN?"
            self._log(cmd, "TX")
            try:
                addrs = self._client.i2c_scan()
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"scan: {len(addrs)} device(s)", "OK")
            self.after(0, lambda: self._set_scan_result(addrs))

        self._run_bg(do)

    def _on_raw_read(self) -> None:
        try:
            addr = self._parse_u8(self._addr_var.get(), "addr")
            length = self._parse_len(self._len_var.get())
        except ValueError as exc:
            self._log(str(exc), "ERR")
            return

        def do():
            cmd = f"I2C1:READ 0x{addr:02X} {length}"
            self._log(cmd, "TX")
            try:
                data = self._client.i2c_read(addr, length)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"RX {len(data)} bytes: {format_hex(data)}", "RX")
            self.after(0, lambda: self._set_rx(data))

        self._run_bg(do)

    def _on_raw_write(self) -> None:
        try:
            addr = self._parse_u8(self._addr_var.get(), "addr")
            data = parse_hex(self._tx_text.get("1.0", "end"))
        except ValueError as exc:
            self._log(str(exc), "ERR")
            return
        if not data:
            self._log("TX data 為空", "ERR")
            return
        if len(data) > 64:
            self._log(f"TX data {len(data)} bytes 超過 64", "ERR")
            return

        def do():
            cmd = f"I2C1:WRITE 0x{addr:02X} " + " ".join(f"0x{b:02X}" for b in data)
            self._log(cmd, "TX")
            try:
                self._client.i2c_write(addr, data)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"OK ({len(data)} bytes written)", "OK")

        self._run_bg(do)

    def _on_mem_read(self) -> None:
        try:
            addr = self._parse_u8(self._addr_var.get(), "addr")
            reg = self._parse_u8(self._reg_var.get(), "reg")
            length = self._parse_len(self._len_var.get())
        except ValueError as exc:
            self._log(str(exc), "ERR")
            return

        def do():
            cmd = f"I2C1:MEMREAD 0x{addr:02X} 0x{reg:02X} {length}"
            self._log(cmd, "TX")
            try:
                data = self._client.i2c_mem_read(addr, reg, length)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"RX {len(data)} bytes: {format_hex(data)}", "RX")
            self.after(0, lambda: self._set_rx(data))

        self._run_bg(do)

    def _on_recover(self) -> None:
        def do():
            self._log("I2C1:RECOVER", "TX")
            try:
                ok, idle = self._client.i2c_bus_recover()
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._set_bus_idle_indicator(None))
                return
            self._log(f"recover OK  bus_idle={int(idle)}",
                      "OK" if idle else "WARN")
            self.after(0, lambda: self._set_bus_idle_indicator(idle))

        self._run_bg(do)

    def _on_check_bus(self) -> None:
        def do():
            self._log("I2C1:BUSIDLE?", "TX")
            try:
                idle = self._client.i2c_bus_idle()
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._set_bus_idle_indicator(None))
                return
            self._log(f"bus_idle={int(idle)}", "OK" if idle else "WARN")
            self.after(0, lambda: self._set_bus_idle_indicator(idle))

        self._run_bg(do)

    def _set_bus_idle_indicator(self, idle: Optional[bool]) -> None:
        if idle is None:
            self._bus_idle_var.set("bus: err")
            self._bus_idle_label.configure(foreground="#c00000")
        elif idle:
            self._bus_idle_var.set("bus: idle")
            self._bus_idle_label.configure(foreground="#1a7f37")
        else:
            self._bus_idle_var.set("bus: STUCK")
            self._bus_idle_label.configure(foreground="#c00000")

    def _on_mem_write(self) -> None:
        try:
            addr = self._parse_u8(self._addr_var.get(), "addr")
            reg = self._parse_u8(self._reg_var.get(), "reg")
            data = parse_hex(self._tx_text.get("1.0", "end"))
        except ValueError as exc:
            self._log(str(exc), "ERR")
            return
        if not data:
            self._log("TX data 為空", "ERR")
            return
        if len(data) > 64:
            self._log(f"TX data {len(data)} bytes 超過 64", "ERR")
            return

        def do():
            cmd = (f"I2C1:MEMWRITE 0x{addr:02X} 0x{reg:02X} "
                   + " ".join(f"0x{b:02X}" for b in data))
            self._log(cmd, "TX")
            try:
                self._client.i2c_mem_write(addr, reg, data)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                return
            self._log(f"OK ({len(data)} bytes written to reg 0x{reg:02X})", "OK")

        self._run_bg(do)
