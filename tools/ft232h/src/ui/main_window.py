"""主視窗：頂端裝置選擇列 + 三個分頁 (GPIO / SPI / I2C) + 共用 log。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.device import DeviceInfo, default_url, list_devices
from .gpio_tab import GpioTab
from .i2c_tab import I2cTab
from .log_panel import LogPanel
from .spi_tab import SpiTab


APP_TITLE = "FT232H Tester"
APP_VERSION = "0.1.0"


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.geometry("820x720")
        self.minsize(780, 600)

        self._devices: list[DeviceInfo] = []
        self._build()
        self._refresh_devices(initial=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        # ---- 頂端裝置列 ----
        top = ttk.LabelFrame(self, text="Device")
        top.pack(side="top", fill="x", padx=8, pady=6)

        ttk.Label(top, text="URL:").pack(side="left", padx=(8, 4))
        self._url_var = tk.StringVar(value=default_url())
        self._url_combo = ttk.Combobox(top, textvariable=self._url_var, width=60)
        self._url_combo.pack(side="left", fill="x", expand=True, padx=4)

        ttk.Button(top, text="Refresh", command=self._refresh_devices, width=10).pack(side="left", padx=4)

        # ---- 分頁 ----
        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        self._log_panel = LogPanel(self)
        self._log_panel.pack(side="bottom", fill="x", padx=8, pady=(0, 6))

        get_url = lambda: self._url_var.get().strip()
        log = self._log_panel.log

        self._gpio_tab = GpioTab(nb, get_url, log)
        self._spi_tab = SpiTab(nb, get_url, log)
        self._i2c_tab = I2cTab(nb, get_url, log)

        nb.add(self._gpio_tab, text="GPIO")
        nb.add(self._spi_tab, text="SPI")
        nb.add(self._i2c_tab, text="I2C")

        self._status = ttk.Label(self, text="Ready", anchor="w", relief="sunken")
        self._status.pack(side="bottom", fill="x")

    def _refresh_devices(self, initial: bool = False) -> None:
        try:
            self._devices = list_devices()
        except Exception as ex:
            self._log_panel.log(f"list_devices failed: {ex}", "ERR")
            self._devices = []

        urls = [d.url for d in self._devices]
        if not urls:
            self._url_combo["values"] = [default_url()]
            if initial:
                self._log_panel.log("No FT232H found. 確認 USB 已插入且 driver 用 Zadig 換成 libusbK/WinUSB", "WARN")
            else:
                self._log_panel.log("No FT232H found", "WARN")
        else:
            self._url_combo["values"] = urls
            if not self._url_var.get() or self._url_var.get() not in urls:
                self._url_var.set(urls[0])
            self._log_panel.log(f"Found {len(self._devices)} device(s)", "OK")
            for d in self._devices:
                self._log_panel.log(f"  {d.display}", "INFO")

        self._status.configure(text=f"Devices: {len(self._devices)}")

    def _on_close(self) -> None:
        for tab in (self._gpio_tab, self._spi_tab, self._i2c_tab):
            try:
                tab.on_app_close()
            except Exception:
                pass
        self.destroy()
