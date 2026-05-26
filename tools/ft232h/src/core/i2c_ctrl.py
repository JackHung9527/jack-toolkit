"""FT232H I2C master 控制封裝。

FT232H MPSSE I2C pinout（必須外接 pull-up 到 VCC，建議 4.7k）：
    AD0 = SCL
    AD1 + AD2 短接 = SDA  (因為 FT232H 沒有真正的 open-drain)

支援頻率：100 kHz / 400 kHz / 1 MHz (HS)。
"""

from __future__ import annotations

from typing import List, Optional

from pyftdi.i2c import I2cController, I2cNackError


DEFAULT_FREQUENCY = 100_000


class I2cCtrl:
    """I2C master 控制器。"""

    def __init__(self) -> None:
        self._ctl: Optional[I2cController] = None
        self._frequency: int = DEFAULT_FREQUENCY

    @property
    def is_open(self) -> bool:
        return self._ctl is not None

    def open(self, url: str, frequency_hz: int = DEFAULT_FREQUENCY) -> None:
        if self._ctl is not None:
            self.close()
        ctl = I2cController()
        ctl.configure(url, frequency=frequency_hz)
        self._ctl = ctl
        self._frequency = frequency_hz

    def close(self) -> None:
        if self._ctl is not None:
            try:
                self._ctl.terminate()
            except Exception:
                pass
            self._ctl = None

    def scan(self, start: int = 0x03, end: int = 0x77) -> List[int]:
        """掃描 7-bit I2C address，回傳有 ACK 的位址清單。"""
        self._require_open()
        found: List[int] = []
        for addr in range(start, end + 1):
            try:
                port = self._ctl.get_port(addr)
                # 用 0-byte write 偵測 ACK；FT232H 不支援 0-byte 時 fallback 用 1-byte read
                try:
                    port.write(b"")
                except Exception:
                    port.read(1)
                found.append(addr)
            except I2cNackError:
                continue
            except Exception:
                continue
        return found

    def write(self, address: int, data: bytes) -> None:
        self._require_open()
        port = self._ctl.get_port(address)
        port.write(data)

    def read(self, address: int, length: int) -> bytes:
        self._require_open()
        port = self._ctl.get_port(address)
        return bytes(port.read(length))

    def write_read(self, address: int, out_data: bytes, in_length: int) -> bytes:
        """write 後接 repeated-start read，常用於 register read。"""
        self._require_open()
        port = self._ctl.get_port(address)
        return bytes(port.exchange(out_data, in_length))

    def read_reg(self, address: int, reg: int, length: int = 1) -> bytes:
        return self.write_read(address, bytes([reg & 0xFF]), length)

    def write_reg(self, address: int, reg: int, data: bytes) -> None:
        self.write(address, bytes([reg & 0xFF]) + data)

    @property
    def frequency(self) -> int:
        return self._frequency

    def _require_open(self) -> None:
        if self._ctl is None:
            raise RuntimeError("I2C not opened")
