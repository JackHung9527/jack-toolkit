"""FT232H 裝置掃描與 URL 管理。

FT232H 是單通道 USB 轉多協議橋接晶片，pyftdi 用 URL 描述裝置：
    ftdi://ftdi:232h:<serial>/1
    ftdi://ftdi:232h/1            (只接一顆時可省略序號)

本模組只負責掃描與 URL 組裝，實際開啟交給 GPIO / SPI / I2C controller。
三種協議互斥：同一個 FT232H 一次只能用一種模式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pyftdi.ftdi import Ftdi


# FT232H 預設 VID/PID（FTDI 官方）
FTDI_VID = 0x0403
FT232H_PID = 0x6014


@dataclass
class DeviceInfo:
    """單顆 FT232H 的描述資訊。"""

    url: str
    serial: str
    description: str
    vid: int
    pid: int

    @property
    def display(self) -> str:
        """供 UI 下拉選單顯示的字串。"""
        serial_text = self.serial if self.serial else "(no-serial)"
        return f"{serial_text} | {self.description} [{self.url}]"


def list_devices() -> List[DeviceInfo]:
    """掃描目前連線的所有 FT232H 裝置。

    回傳空 list 表示沒抓到，常見原因：
        1. 沒插
        2. Windows 上沒用 Zadig 把 driver 換成 libusbK / WinUSB
        3. 被其他 process 占用
    """
    devices: List[DeviceInfo] = []
    # 故意不吞例外：UI 端會 catch 並顯示真正的錯誤訊息。
    raw_list = Ftdi.list_devices("ftdi://ftdi:232h/?")

    for desc, _interface in raw_list:
        serial = desc.sn or ""
        url = f"ftdi://ftdi:232h:{serial}/1" if serial else "ftdi://ftdi:232h/1"
        devices.append(
            DeviceInfo(
                url=url,
                serial=serial,
                description=desc.description or "FT232H",
                vid=desc.vid,
                pid=desc.pid,
            )
        )
    return devices


def default_url() -> str:
    """單顆裝置時可直接使用的預設 URL。"""
    return "ftdi://ftdi:232h/1"
