"""FT232H GPIO 控制封裝。

FT232H 有 16 個可用 GPIO：
    ADBUS0..ADBUS7  (低 8 bits, bit 0..7)
    ACBUS0..ACBUS7  (高 8 bits, bit 8..15)

pyftdi 的 GpioMpsseController 把這 16 個合併成 16-bit word：
    bit  0 -> AD0 (SCK)
    bit  1 -> AD1 (MOSI)
    bit  2 -> AD2 (MISO)
    bit  3 -> AD3 (CS)
    bit  4 -> AD4
    ...
    bit 15 -> AC7

direction bit 1 = output, 0 = input。
"""

from __future__ import annotations

from typing import Optional

from pyftdi.gpio import GpioMpsseController


PIN_COUNT = 16


PIN_NAMES = [
    "AD0", "AD1", "AD2", "AD3", "AD4", "AD5", "AD6", "AD7",
    "AC0", "AC1", "AC2", "AC3", "AC4", "AC5", "AC6", "AC7",
]


class GpioController:
    """16-pin GPIO 控制器，全部走 MPSSE，速度預設 1 MHz。"""

    def __init__(self) -> None:
        self._gpio: Optional[GpioMpsseController] = None
        self._direction: int = 0x0000  # 全部預設 input
        self._output_cache: int = 0x0000

    @property
    def is_open(self) -> bool:
        return self._gpio is not None

    def open(self, url: str, frequency_hz: int = 1_000_000) -> None:
        """開啟 FT232H 並把全部 16 pin 設成 input。"""
        if self._gpio is not None:
            self.close()
        gpio = GpioMpsseController()
        gpio.configure(url, direction=0x0000, frequency=frequency_hz)
        self._gpio = gpio
        self._direction = 0x0000
        self._output_cache = 0x0000

    def close(self) -> None:
        if self._gpio is not None:
            try:
                self._gpio.close()
            except Exception:
                pass
            self._gpio = None

    def set_direction(self, pin: int, is_output: bool) -> None:
        """設定單一 pin 方向。"""
        self._require_open()
        if not (0 <= pin < PIN_COUNT):
            raise ValueError(f"pin index {pin} out of range")
        if is_output:
            self._direction |= (1 << pin)
        else:
            self._direction &= ~(1 << pin)
        # 重新套用 direction（pyftdi 沒提供 partial update，需重 configure pins）
        self._gpio.set_direction(0xFFFF, self._direction)

    def write_pin(self, pin: int, level: bool) -> None:
        """寫入單一 output pin。input pin 寫入無效但不報錯。"""
        self._require_open()
        if not (0 <= pin < PIN_COUNT):
            raise ValueError(f"pin index {pin} out of range")
        if level:
            self._output_cache |= (1 << pin)
        else:
            self._output_cache &= ~(1 << pin)
        # 只送 direction 為 output 的 bit；input bit 維持 0
        masked = self._output_cache & self._direction
        self._gpio.write(masked)

    def read_all(self) -> int:
        """讀回 16-bit 即時 pin 狀態。

        pyftdi 0.57 的 GpioMpsseController.read(readlen=1) 回 tuple，
        舊版本可能回 int / list / bytes，這裡四種都吃。
        """
        self._require_open()
        value = self._gpio.read()

        if isinstance(value, int):
            return value & 0xFFFF
        if isinstance(value, (tuple, list)):
            if len(value) == 0:
                return 0
            return int(value[0]) & 0xFFFF
        if isinstance(value, (bytes, bytearray)):
            if len(value) == 0:
                return 0
            if len(value) == 1:
                return value[0]
            return (value[0] | (value[1] << 8)) & 0xFFFF
        # 未知型別兜底
        try:
            return int(value) & 0xFFFF
        except Exception:
            return 0

    def read_pin(self, pin: int) -> bool:
        word = self.read_all()
        return bool((word >> pin) & 0x1)

    def get_direction(self) -> int:
        return self._direction

    def _require_open(self) -> None:
        if self._gpio is None:
            raise RuntimeError("GPIO not opened")
