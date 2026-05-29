"""FT232H 裝置掃描與 URL 管理。

FT232H 是單通道 USB 轉多協議橋接晶片，pyftdi 用 URL 描述裝置：
    ftdi://ftdi:232h:<serial>/1
    ftdi://ftdi:232h/1            (只接一顆時可省略序號)

本模組只負責掃描與 URL 組裝，實際開啟交給 GPIO / SPI / I2C controller。
三種協議互斥：同一個 FT232H 一次只能用一種模式。

實測踩雷：FT232H 在 driver swap 後 (Zadig 換成 WinUSB) 偶爾會卡在「半死狀態」——
libusb 能 enumerate 看到 device，但所有 GET_DESCRIPTOR 都 timeout。
解法：跑 pyftdi.list_devices 之前先對每個 FT232H 送 USB-level reset，
強制 device 重新初始化 endpoint 狀態。reset 對正常 device 也無害。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from pyftdi.ftdi import Ftdi


# FT232H 預設 VID/PID（FTDI 官方）
FTDI_VID = 0x0403
FT232H_PID = 0x6014

_log = logging.getLogger(__name__)


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


def _reset_all_ft232h() -> int:
    """對系統上所有 FT232H (PID=6014) 送 USB reset，解決「半死狀態」。

    為了在 Windows + WinUSB 上拿到 reset 權限，先 claim_interface 才能 reset，
    這樣 libusb 能跟 kernel 拿 exclusive write handle。reset 完釋放。
    回傳成功 reset 的 device 數量；失敗的 device 跳過（log warning，不丟例外）。
    """
    try:
        import libusb_package
        import usb.backend.libusb1 as b1
        import usb.core
        import usb.util
    except ImportError:
        return 0

    backend = b1.get_backend(find_library=libusb_package.find_library)
    if backend is None:
        return 0

    try:
        devs = list(usb.core.find(
            find_all=True,
            idVendor=FTDI_VID,
            idProduct=FT232H_PID,
            backend=backend,
        ))
    except Exception as exc:
        _log.warning("usb.core.find failed: %r", exc)
        return 0

    count = 0
    for d in devs:
        claimed = False
        try:
            usb.util.claim_interface(d, 0)
            claimed = True
            d.reset()
            count += 1
        except Exception as exc:
            _log.warning("USB reset failed for bus=%s addr=%s: %r", d.bus, d.address, exc)
        finally:
            if claimed:
                try:
                    usb.util.release_interface(d, 0)
                except Exception:
                    pass
            try:
                usb.util.dispose_resources(d)
            except Exception:
                pass
    return count


def list_devices() -> List[DeviceInfo]:
    """掃描目前連線的所有 FT232H 裝置。

    回傳空 list 表示沒抓到，常見原因：
        1. 沒插
        2. Windows 上沒用 Zadig 把 driver 換成 libusbK / WinUSB
        3. 被其他 process 占用

    在 pyftdi list 之前先對所有 FT232H 送 USB reset，解決常見「driver 換完
    但 device 卡在半死狀態」的問題。
    """
    _reset_all_ft232h()

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
