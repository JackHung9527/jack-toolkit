"""FT232H SPI master 控制封裝。

FT232H 用 MPSSE engine 做 SPI，pinout 固定：
    AD0 = SCK
    AD1 = MOSI (FT232H -> slave)
    AD2 = MISO (slave  -> FT232H)
    AD3 = CS0 (預設)
    AD4 = CS1
    AD5 = CS2
    AD6 = CS3
    AD7 = CS4

最高 clock ~30 MHz，實務上 6~10 MHz 比較穩。
mode 0/1/2/3 對應 CPOL/CPHA：
    mode 0: CPOL=0, CPHA=0
    mode 1: CPOL=0, CPHA=1
    mode 2: CPOL=1, CPHA=0
    mode 3: CPOL=1, CPHA=1
"""

from __future__ import annotations

from typing import Optional

from pyftdi.spi import SpiController, SpiPort


CS_LINE_COUNT = 5  # AD3..AD7
DEFAULT_FREQUENCY = 1_000_000


class SpiCtrl:
    """SPI master 控制器，支援多個 CS。"""

    def __init__(self) -> None:
        self._ctl: Optional[SpiController] = None
        self._port: Optional[SpiPort] = None
        self._cs: int = 0
        self._mode: int = 0
        self._frequency: int = DEFAULT_FREQUENCY

    @property
    def is_open(self) -> bool:
        return self._ctl is not None

    def open(self, url: str, cs: int = 0, frequency_hz: int = DEFAULT_FREQUENCY, mode: int = 0) -> None:
        if self._ctl is not None:
            self.close()
        if not (0 <= cs < CS_LINE_COUNT):
            raise ValueError(f"cs {cs} out of range (0..{CS_LINE_COUNT - 1})")
        if mode not in (0, 1, 2, 3):
            raise ValueError(f"SPI mode {mode} invalid")

        ctl = SpiController(cs_count=CS_LINE_COUNT)
        ctl.configure(url, frequency=frequency_hz)
        port = ctl.get_port(cs=cs, freq=frequency_hz, mode=mode)
        self._ctl = ctl
        self._port = port
        self._cs = cs
        self._mode = mode
        self._frequency = frequency_hz

    def close(self) -> None:
        self._port = None
        if self._ctl is not None:
            try:
                self._ctl.terminate()
            except Exception:
                pass
            self._ctl = None

    def write(self, data: bytes) -> None:
        self._require_open()
        self._port.write(data)

    def read(self, length: int) -> bytes:
        self._require_open()
        if length <= 0:
            return b""
        return bytes(self._port.read(length))

    def exchange(self, out_data: bytes, in_length: int = 0, duplex: bool = False) -> bytes:
        """送 + 收。

        duplex=True 表示同時送收（full-duplex），回傳長度 = len(out_data)。
        duplex=False 表示先送後收（half-duplex），回傳長度 = in_length。
        """
        self._require_open()
        if duplex:
            if in_length not in (0, len(out_data)):
                raise ValueError("full-duplex: in_length must be 0 or equal to len(out_data)")
            return bytes(self._port.exchange(out_data, len(out_data), duplex=True))
        return bytes(self._port.exchange(out_data, in_length, duplex=False))

    @property
    def cs(self) -> int:
        return self._cs

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def frequency(self) -> int:
        return self._frequency

    def _require_open(self) -> None:
        if self._port is None:
            raise RuntimeError("SPI not opened")
