"""CommBench host UI 主視窗。

頂端：COM port 選擇 + 自動偵測 + Open/Close
分頁：接線圖 / I2C / SCPI Console
底部：log panel + 狀態列

「自動偵測」會：
  (1) 用 ST-Link USB VID (0483) + 描述字串過濾出候選 port
  (2) 對每個候選 port 開埠並送 *IDN?
  (3) 認到回應含 'CommBench' 且 'STM32G071' 的那一片就鎖定
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..core.scpi_client import (
    PortInfo,
    ScpiClient,
    ScpiError,
    auto_detect_commbench,
    guess_nucleo_port,
    list_ports,
)
from .console_tab import ConsoleTab
from .i2c_tab import I2cTab
from .log_panel import LogPanel
from .pinout_tab import PinoutTab
from .pmbus_tab import PmbusTab


APP_TITLE = "CommBench (G071) Host"
APP_VERSION = "0.1.0"


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.geometry("980x780")
        self.minsize(900, 640)

        self._client = ScpiClient()
        self._ports: list[PortInfo] = []
        self._build()
        self._refresh_ports(initial=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- build ----------------

    def _build(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        # === 頂端 Device bar ===
        top = ttk.LabelFrame(self, text="Device")
        top.pack(side="top", fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text="COM port:").pack(side="left", padx=(8, 4))
        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(top, textvariable=self._port_var,
                                        width=42, font=("Consolas", 9))
        self._port_combo.pack(side="left", padx=4)

        self._refresh_btn = ttk.Button(top, text="Refresh", width=9,
                                       command=lambda: self._refresh_ports(initial=False))
        self._refresh_btn.pack(side="left", padx=2)

        self._auto_btn = ttk.Button(top, text="Auto detect", width=12,
                                    command=self._on_auto_detect)
        self._auto_btn.pack(side="left", padx=2)

        self._open_btn = ttk.Button(top, text="Open", width=8, command=self._on_open)
        self._open_btn.pack(side="left", padx=(8, 2))
        self._close_btn = ttk.Button(top, text="Close", width=8, state="disabled",
                                     command=self._on_close_port)
        self._close_btn.pack(side="left", padx=2)

        # IDN display
        self._idn_var = tk.StringVar(value="(未連線)")
        ttk.Label(top, textvariable=self._idn_var,
                  font=("Segoe UI", 9, "bold"), foreground="#1a7f37").pack(
            side="left", padx=(12, 8))

        # === 分頁 ===
        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        # log panel 要先建好給其它分頁用
        self._log_panel = LogPanel(self)
        self._log_panel.pack(side="bottom", fill="both", padx=8, pady=(0, 4))

        log = self._log_panel.log

        self._pinout_tab = PinoutTab(nb, get_connected=self._client.is_open)
        self._i2c_tab = I2cTab(nb, self._client, log)
        self._pmbus_tab = PmbusTab(nb, self._client, log)
        self._console_tab = ConsoleTab(nb, self._client, log)

        nb.add(self._pinout_tab, text="接線圖")
        nb.add(self._i2c_tab, text="I2C")
        nb.add(self._pmbus_tab, text="PMBus")
        nb.add(self._console_tab, text="SCPI Console")

        # 狀態列
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self._status_var, anchor="w",
                  relief="sunken").pack(side="bottom", fill="x")

    # ---------------- port handling ----------------

    def _refresh_ports(self, initial: bool = False) -> None:
        try:
            self._ports = list_ports()
        except Exception as exc:
            self._log_panel.log(f"list_ports failed: {exc}", "ERR")
            self._ports = []

        display = []
        for p in self._ports:
            tag = "[STLink] " if p.is_stlink else ""
            display.append(f"{tag}{p.device}  —  {p.description}")
        self._port_combo["values"] = display

        # 預選 ST-Link 那一條
        guess = guess_nucleo_port(self._ports)
        if guess:
            for i, p in enumerate(self._ports):
                if p.device == guess:
                    self._port_combo.current(i)
                    break
            if initial:
                self._log_panel.log(f"偵測到 ST-Link VCP: {guess}", "INFO")
        elif self._ports and not self._port_var.get():
            self._port_combo.current(0)

        self._status_var.set(f"COM ports: {len(self._ports)}")

        if initial and not self._ports:
            self._log_panel.log("沒找到任何 COM port。先確認 NUCLEO 已經接 USB。", "WARN")

    def _selected_device(self) -> Optional[str]:
        idx = self._port_combo.current()
        if 0 <= idx < len(self._ports):
            return self._ports[idx].device
        # 使用者手打的字串：取開頭 token 當 device
        text = self._port_var.get().strip()
        if not text:
            return None
        # 形式可能是 "[STLink] COM5  —  ..."
        for tok in text.replace("—", " ").split():
            if tok.upper().startswith("COM") or tok.startswith("/"):
                return tok
        return text.split()[0]

    def _on_auto_detect(self) -> None:
        """背景跑 auto_detect_commbench()，命中後鎖定 port 並自動開埠。"""
        self._log_panel.log("Auto detect 開始 — 掃描所有 ST-Link port 並送 *IDN?...", "INFO")
        self._auto_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")

        def _worker():
            found: Optional[str] = None
            try:
                found = auto_detect_commbench(timeout_per_port_s=0.8)
            except Exception as exc:
                self.after(0, lambda: self._log_panel.log(f"Auto detect 例外: {exc}", "ERR"))

            def _done():
                self._auto_btn.configure(state="normal")
                self._open_btn.configure(state="normal")
                self._refresh_ports(initial=False)
                if found is None:
                    self._log_panel.log("Auto detect 沒命中 — 沒有 port 回應 CommBench *IDN?", "WARN")
                    messagebox.showwarning(
                        "Auto detect",
                        "沒找到 CommBench / G071 板。\n\n"
                        "請確認：\n"
                        "  1. NUCLEO 已接 USB\n"
                        "  2. CommBench 韌體已燒錄\n"
                        "  3. 另一個程式沒有佔住 VCP COM port",
                    )
                    return
                # 把 found 設成 combo 選項
                for i, p in enumerate(self._ports):
                    if p.device == found:
                        self._port_combo.current(i)
                        break
                self._log_panel.log(f"Auto detect 命中: {found} — 自動開啟", "OK")
                self._on_open()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_open(self) -> None:
        """非阻塞 Open：把 open() + verify_idn() 丟到背景 thread，UI 立刻釋放。

        UI 端先 disable Open 按鈕 + 提示連線中，背景做完用 after() 把結果 dispatch
        回 UI thread 做後續顯示（messagebox / log / 連線狀態更新）。
        """
        device = self._selected_device()
        if not device:
            self._log_panel.log("沒選 COM port", "ERR")
            return

        # UI 立刻反應，避免使用者重複按或 Windows 標 "Not Responding"
        self._open_btn.configure(state="disabled")
        self._auto_btn.configure(state="disabled")
        self._refresh_btn.configure(state="disabled")
        self._status_var.set(f"連線中 {device}...")
        self._log_panel.log(f"開啟 {device}...", "INFO")

        def _worker():
            err_msg = None
            matched = False
            idn = ""
            try:
                self._client.open(device)
            except Exception as exc:
                err_msg = ("open_fail", str(exc))
                self.after(0, lambda: self._on_open_done(device, err_msg, matched, idn))
                return

            try:
                matched, idn = self._client.verify_idn()
            except ScpiError as exc:
                err_msg = ("verify_fail", str(exc))
            except Exception as exc:
                err_msg = ("verify_fail", str(exc))

            self.after(0, lambda: self._on_open_done(device, err_msg, matched, idn))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_open_done(self, device: str, err: Optional[tuple[str, str]],
                       matched: bool, idn: str) -> None:
        """背景 worker 完成後在 UI thread 呼叫，做後續顯示與狀態更新。"""
        # 還原按鈕狀態（後面若連線成功會由 _on_connection_changed 接管）
        self._open_btn.configure(state="normal")
        self._auto_btn.configure(state="normal")
        self._refresh_btn.configure(state="normal")

        if err is not None:
            kind, msg = err
            try:
                self._client.close()
            except Exception:
                pass
            if kind == "open_fail":
                self._log_panel.log(f"開啟 {device} 失敗: {msg}", "ERR")
                self._status_var.set("Disconnected")
                messagebox.showerror("Open 失敗", f"{device}\n\n{msg}")
            else:
                self._log_panel.log(f"*IDN? 失敗: {msg}", "ERR")
                self._status_var.set("Disconnected")
                messagebox.showerror(
                    "握手失敗",
                    f"開啟 {device} 成功但 *IDN? 沒回應或回應異常。\n\n"
                    f"{msg}\n\n可能不是 CommBench 韌體，或 baud rate 不對。",
                )
            return

        if not matched:
            self._log_panel.log(f"*IDN? 回應 = {idn!r}", "WARN")
            ok = messagebox.askyesno(
                "不是 CommBench 韌體",
                f"{device} 回應的 *IDN? 首欄不是 'CommBench'：\n\n"
                f"  {idn or '(空)'}\n\n"
                "仍然繼續使用嗎？\n（這片板可能跑的是別的韌體，命令會 ERR）",
            )
            if not ok:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._log_panel.log("使用者取消連線", "INFO")
                self._status_var.set("Disconnected")
                return
        else:
            if not self._client.idn_mcu_matches(idn):
                self._log_panel.log(
                    f"注意：IDN 內 MCU 欄位非 STM32G071，實際回應 = {idn}",
                    "WARN",
                )

        self._log_panel.log(f"已連線 {device}  IDN = {idn or '(空)'}", "OK")
        self._idn_var.set(idn or f"已連線 {device}")
        self._on_connection_changed(True)

    def _on_close_port(self) -> None:
        if self._client.is_open():
            self._log_panel.log(f"關閉 {self._client.port_name}", "INFO")
            self._client.close()
        self._idn_var.set("(未連線)")
        self._on_connection_changed(False)

    def _on_connection_changed(self, connected: bool) -> None:
        self._open_btn.configure(state="disabled" if connected else "normal")
        self._close_btn.configure(state="normal" if connected else "disabled")
        self._refresh_btn.configure(state="disabled" if connected else "normal")
        self._auto_btn.configure(state="disabled" if connected else "normal")
        self._port_combo.configure(state="disabled" if connected else "normal")
        self._i2c_tab.set_connected(connected)
        self._pmbus_tab.set_connected(connected)
        self._console_tab.set_connected(connected)
        self._pinout_tab.refresh()
        self._status_var.set(
            f"Connected: {self._client.port_name}" if connected else "Disconnected"
        )

    def _on_close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        self.destroy()
