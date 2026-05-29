"""SCPI / VCP transport for CommBench G071 firmware.

韌體（USER_CODE/scpi/scpi.c）在 LPUART1（ST-Link VCP）@ 115200 8N1 跑 SCPI
風格命令解析器；每個命令以 LF/CRLF 終止，回應一律 \\r\\n。

本檔提供：
    - list_ports()                列出系統 COM port + 描述
    - guess_nucleo_port()         猜哪個是 NUCLEO 板（描述含 "STLink" / "STMicro"）
    - ScpiClient                  thread-safe 同步請求介面
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    from serial import Serial, SerialException
    from serial.tools import list_ports as _list_ports
except ImportError as exc:
    raise ImportError(
        "缺少 pyserial。請執行：pip install pyserial"
    ) from exc


DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT_S = 1.5
LINE_TERMINATOR = b"\r\n"

# 韌體 *IDN? 回應：CommBench,STM32G071RB,v0.1
# 認 vendor + MCU 兩段，version 不卡死
EXPECTED_IDN_VENDOR = "CommBench"
EXPECTED_IDN_MCU = "STM32G071"

# ST-Link USB IDs（NUCLEO 板載 ST-Link/V2-1 / V3 都用同一個 vendor）
STLINK_VID = 0x0483
STLINK_PIDS = (0x374B, 0x3748, 0x374E, 0x374F, 0x3753, 0x3754)


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: Optional[int] = None
    pid: Optional[int] = None

    @property
    def display(self) -> str:
        desc = self.description if self.description != "n/a" else ""
        return f"{self.device}  {desc}".strip()

    @property
    def is_stlink(self) -> bool:
        """USB VID == ST-Link（NUCLEO 板載 VCP 共用此 VID）。"""
        if self.vid == STLINK_VID:
            return True
        haystack = f"{self.description} {self.hwid}".lower()
        return ("stlink" in haystack) or ("st-link" in haystack) or ("stmicro" in haystack)


def list_ports() -> list[PortInfo]:
    """列出所有 COM port。"""
    result: list[PortInfo] = []
    for p in _list_ports.comports():
        result.append(
            PortInfo(
                device=p.device,
                description=p.description or "",
                hwid=p.hwid or "",
                vid=getattr(p, "vid", None),
                pid=getattr(p, "pid", None),
            )
        )
    return result


def guess_nucleo_port(ports: list[PortInfo]) -> Optional[str]:
    """挑出最可能是 NUCLEO VCP 的 port（先看 ST-Link VID，再看描述）。

    只能保證「是某張 NUCLEO/ST-Link 板」，不能保證是 G071 或跑著 CommBench；
    確認是不是 CommBench/G071 要走 ScpiClient.verify_idn()。
    """
    # 先看 USB VID（最可靠）
    for p in ports:
        if p.vid == STLINK_VID:
            return p.device
    # 再 fallback 看描述字串
    for p in ports:
        if p.is_stlink:
            return p.device
    return None


def auto_detect_commbench(timeout_per_port_s: float = 0.6) -> Optional[str]:
    """掃所有 ST-Link 描述的 port，依序開啟並送 *IDN?，回傳第一個 CommBench 板。

    如果使用者插了多片 NUCLEO（例如同時插一片 G071 + 一片 H7），
    這個函式會選到回應 *IDN? 含 'CommBench' 的那一片。
    沒命中時回傳 None。
    """
    ports = list_ports()
    # ST-Link 候選排前面，其他 port 排後面（少數情境使用者用 USB-TTL 接 LPUART）
    candidates = sorted(ports, key=lambda p: (0 if p.is_stlink else 1, p.device))
    for p in candidates:
        client = ScpiClient()
        try:
            client.open(p.device, timeout_s=timeout_per_port_s)
            matched, _idn = client.verify_idn()
            if matched:
                client.close()
                return p.device
        except (SerialException, ScpiError, OSError):
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass
    return None


class ScpiError(RuntimeError):
    """SCPI 層錯誤（韌體回傳 ERR / timeout / port 已關閉）。"""


class ScpiClient:
    """跟 G071 SCPI 韌體做同步請求-回應的 client。

    所有 query / command 都會在內部 mutex 鎖內執行；外部多執行緒呼叫安全，
    但因為韌體本身是 single-line request/response，並沒有非同步事件，
    所以呼叫端不需要 polling。
    """

    def __init__(self) -> None:
        self._ser: Optional[Serial] = None
        self._lock = threading.RLock()
        self._port_name: str = ""

    # ---------------- lifecycle ----------------

    def open(self, port: str, baud: int = DEFAULT_BAUD, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        """打開 COM port。

        為避免 Windows 預設「Serial(port=...) 一建構就開啟並 toggle DTR/RTS」
        造成 MCU 端收到雜訊或 RX line buffer 留下半行命令，
        這裡用「延遲開啟」模式：先建 Serial 物件、把 dtr/rts 都 force 成 False、
        再 .open()，可以最大化跳過 DTR pulse 造成的開頭 byte 丟失。

        開完之後做兩件事：
          (a) drain 一輪殘留資料（清掉開埠瞬間 USB CDC FIFO 殘留 / banner）
          (b) 送一個空 \\r\\n 給 MCU，把 MCU 的 RX line buffer 內任何殘留
              半截字元清掉（韌體看到 \\r\\n 就 dispatch 一次，內容空就 ERR
              一次，但這次 ERR 我們不在意，只是要清狀態），再 drain 一輪
        這樣後續 query("*IDN?") 才會拿到乾淨的回應。
        """
        with self._lock:
            self.close()
            ser = Serial()
            ser.port = port
            ser.baudrate = baud
            ser.bytesize = 8
            ser.parity = "N"
            ser.stopbits = 1
            ser.timeout = timeout_s
            ser.write_timeout = timeout_s
            # 抑制 Windows 預設的 DTR/RTS toggle
            ser.dtr = False
            ser.rts = False
            ser.open()
            # 萬一上面那組 setter 在「物件未開啟」狀態下是 no-op（pyserial 某些
            # 版本如此），開啟後再保險打一次。
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass
            self._ser = ser
            self._port_name = port

            time.sleep(0.25)
            self._drain_input(timeout_per_read_s=0.15)
            # 送一個空行清 MCU RX line buffer 殘留
            try:
                ser.write(LINE_TERMINATOR)
                ser.flush()
            except Exception:
                pass
            time.sleep(0.1)
            self._drain_input(timeout_per_read_s=0.15)

    def close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
            self._ser = None
            self._port_name = ""

    def is_open(self) -> bool:
        with self._lock:
            return self._ser is not None and self._ser.is_open

    @property
    def port_name(self) -> str:
        return self._port_name

    # ---------------- low-level ----------------

    def _drain_input(self, timeout_per_read_s: float = 0.08) -> str:
        """把當前 input buffer 內的所有資料拉光。

        timeout_per_read_s 拉長到 80ms 可以容忍 USB CDC scheduling 抖動
        （ST-Link VCP 常常一輪一輪丟，中間隔 20-50ms）。
        """
        ser = self._ser
        if ser is None:
            return ""
        chunks: list[bytes] = []
        ser.timeout = timeout_per_read_s
        try:
            while True:
                data = ser.read(512)
                if not data:
                    break
                chunks.append(data)
        finally:
            ser.timeout = DEFAULT_TIMEOUT_S
        return b"".join(chunks).decode("utf-8", errors="replace")

    def _write_line(self, line: str) -> None:
        ser = self._ser
        if ser is None or not ser.is_open:
            raise ScpiError("port not open")
        payload = line.rstrip("\r\n").encode("ascii", errors="replace") + LINE_TERMINATOR
        ser.write(payload)
        ser.flush()

    def _read_lines_until_idle(self, idle_ms: int = 120, max_wait_s: float = 3.0) -> list[str]:
        """讀 response 直到沒有新資料持續 idle_ms 為止。

        韌體可能對一條命令回多行（例如 HELP? 有 N 行），所以不能只讀一行；
        改用「沒看到新資料超過 idle_ms」當結束條件。
        """
        ser = self._ser
        if ser is None:
            raise ScpiError("port not open")

        end_deadline = time.monotonic() + max_wait_s
        ser.timeout = idle_ms / 1000.0

        buf = bytearray()
        while True:
            data = ser.read(512)
            if data:
                buf.extend(data)
                continue
            if time.monotonic() >= end_deadline:
                break
            break  # 一輪沒新資料就視為 idle 結束

        ser.timeout = DEFAULT_TIMEOUT_S
        text = buf.decode("utf-8", errors="replace")
        return [ln for ln in text.replace("\r\n", "\n").split("\n") if ln != ""]

    # ---------------- high-level ----------------

    def query(self, cmd: str, idle_ms: int = 120) -> list[str]:
        """送一條 SCPI 命令並收回回應（list of lines）。"""
        with self._lock:
            if not self.is_open():
                raise ScpiError("port not open")
            self._drain_input()  # 清掉殘留
            self._write_line(cmd)
            lines = self._read_lines_until_idle(idle_ms=idle_ms)
            return lines

    def command(self, cmd: str, idle_ms: int = 120) -> str:
        """送一條命令並期待單行 'OK' / 'ERR ...' 回應。

        回傳整段 raw response（多行則用 '\\n' 連起來）。
        韌體如果回 ERR 開頭，會丟 ScpiError。
        """
        lines = self.query(cmd, idle_ms=idle_ms)
        if not lines:
            raise ScpiError(f"no response to: {cmd}")
        joined = "\n".join(lines)
        if any(ln.lstrip().upper().startswith("ERR") for ln in lines):
            raise ScpiError(joined)
        return joined

    # ---------------- typed helpers ----------------

    def idn(self) -> str:
        """`*IDN?` → 從回應裡找出 IDN 字串。

        韌體本來只應該回一行 `CommBench,STM32G071RB,v0.1`，但實務上會碰到：
          - 開埠瞬間殘留的 banner（`CommBench ready. Type HELP?...`）跟 IDN 同
            batch 進來
          - USB CDC 把 banner 跟 IDN 切在同一個 packet
        所以這裡不再硬拿 lines[0]，改成「掃整批 lines，找看起來最像 IDN 的那行」：
        以「,」分欄、≥3 欄、首欄等於或包含 EXPECTED_IDN_VENDOR 的為優先；
        都找不到再 fallback lines[0]，並做一次「容錯重送」。
        """
        lines = self.query("*IDN?")
        best = _pick_idn_line(lines)
        if best is not None:
            return best
        # fallback：再重送一次（有時第一次帶到 banner 噪音）
        try:
            lines2 = self.query("*IDN?")
        except Exception:
            lines2 = []
        best2 = _pick_idn_line(lines2)
        if best2 is not None:
            return best2
        # 真的沒命中，回第一行（最舊行為）
        return (lines2 or lines or [""])[0]

    def verify_idn(self) -> tuple[bool, str]:
        """送 *IDN? 並比對是否為 CommBench 韌體。

        判定邏輯（容忍 USB CDC 開頭掉 byte）：
          - 用 _pick_idn_line() 多層次比對首欄 + 第二欄含 STM32
          - 命中任一層即 matched=True
          - banner（無逗號、首欄是 'CommBench ready...'）不會被誤判
        """
        lines = self.query("*IDN?")
        best = _pick_idn_line(lines)
        if best is None:
            # 再重送一次（網路抖動容錯）
            try:
                lines2 = self.query("*IDN?")
                best = _pick_idn_line(lines2)
            except Exception:
                lines2 = []
            if best is None:
                # 都沒命中：拿 lines[0] 當回應字串、matched=False，呼叫端可決定是否繼續
                raw = (lines2 or lines or [""])[0]
                return False, raw
        return True, best

    def idn_mcu_matches(self, raw_idn: str) -> bool:
        """檢查 IDN 字串內 MCU 欄位是否符合預期（STM32G071）— 純資訊用，不影響連線。"""
        return EXPECTED_IDN_MCU.upper() in (raw_idn or "").upper()

    def led(self, on: bool) -> str:
        return self.command("LED:ON" if on else "LED:OFF")

    def i2c_probe(self, addr: int) -> bool:
        """`I2C1:PROBE` → True = ACK / False = NACK。"""
        lines = self.query(f"I2C1:PROBE 0x{addr:02X}")
        if not lines:
            raise ScpiError("no response")
        first = lines[0].strip().upper()
        if first.startswith("ACK"):
            return True
        if first.startswith("NACK"):
            return False
        raise ScpiError(lines[0])

    def i2c_scan(self) -> list[int]:
        """`I2C1:SCAN?` → list of 7-bit addresses。

        韌體回應格式：`found N device(s): 0xXX 0xYY ...`
        """
        lines = self.query("I2C1:SCAN?", idle_ms=200)
        if not lines:
            raise ScpiError("no response")
        text = " ".join(lines)
        # 取 ':' 之後的部分
        if ":" in text:
            tail = text.split(":", 1)[1]
        else:
            tail = text
        addrs: list[int] = []
        for tok in tail.split():
            tok = tok.strip().rstrip(",")
            try:
                addrs.append(int(tok, 0))
            except ValueError:
                continue
        return sorted(set(addrs))

    def i2c_read(self, addr: int, length: int) -> bytes:
        """`I2C1:READ <addr> <len>` → bytes。"""
        lines = self.query(f"I2C1:READ 0x{addr:02X} {length}")
        return _parse_ok_hex(lines)

    def i2c_write(self, addr: int, data: bytes) -> None:
        if not data:
            raise ScpiError("data must not be empty")
        hex_args = " ".join(f"0x{b:02X}" for b in data)
        self.command(f"I2C1:WRITE 0x{addr:02X} {hex_args}")

    def i2c_mem_read(self, addr: int, reg: int, length: int) -> bytes:
        """`I2C1:MEMREAD <addr> <reg> <len>`。"""
        lines = self.query(f"I2C1:MEMREAD 0x{addr:02X} 0x{reg:02X} {length}")
        return _parse_ok_hex(lines)

    def i2c_mem_write(self, addr: int, reg: int, data: bytes) -> None:
        if not data:
            raise ScpiError("data must not be empty")
        hex_args = " ".join(f"0x{b:02X}" for b in data)
        self.command(f"I2C1:MEMWRITE 0x{addr:02X} 0x{reg:02X} {hex_args}")

    def i2c_bus_recover(self) -> tuple[bool, bool]:
        """`I2C1:RECOVER` → (success, bus_idle_after_recovery)。

        韌體做 GPIO 層 unstuck（DeInit → bit-bang ≤9 個 SCL clock + STOP → ReInit），
        然後回報 bus 是否回到 idle。完整流程 ~15ms。
        """
        lines = self.query("I2C1:RECOVER", idle_ms=200)
        if not lines:
            raise ScpiError("no response to I2C1:RECOVER")
        text = lines[0].strip()
        ok = text.upper().startswith("OK")
        # 解析 bus_idle=N
        bus_idle = False
        for tok in text.split():
            if tok.startswith("bus_idle="):
                try:
                    bus_idle = bool(int(tok.split("=", 1)[1]))
                except ValueError:
                    pass
        if not ok:
            raise ScpiError(text)
        return ok, bus_idle

    # ---------------- PMBus helpers ----------------

    def pmbus_pec_get(self) -> bool:
        """PMBUS:PEC? → 是否啟用 PEC"""
        lines = self.query("PMBUS:PEC?")
        if not lines:
            raise ScpiError("no response")
        try:
            return bool(int(lines[0].strip()))
        except ValueError as exc:
            raise ScpiError(f"bad pec response: {lines[0]!r}") from exc

    def pmbus_pec_set(self, enabled: bool) -> None:
        """PMBUS:PEC 0|1 → 開關 PEC（韌體預設 ON）"""
        self.command(f"PMBUS:PEC {1 if enabled else 0}")

    def pmbus_op_read(self, addr: int, pec: bool = True) -> int:
        """PMBUS:OP? <addr> <pec> → OPERATION byte (0x00-0xFF)"""
        return self._pmbus_read_ok_byte(f"PMBUS:OP? 0x{addr:02X} {1 if pec else 0}")

    def pmbus_op_write(self, addr: int, value: int, pec: bool = True) -> None:
        """PMBUS:OP <addr> <byte> <pec> → write OPERATION"""
        self.command(f"PMBUS:OP 0x{addr:02X} 0x{value & 0xFF:02X} {1 if pec else 0}")

    def pmbus_onoff_read(self, addr: int, pec: bool = True) -> int:
        """PMBUS:ONOFF? <addr> <pec> → ON_OFF_CONFIG byte"""
        return self._pmbus_read_ok_byte(f"PMBUS:ONOFF? 0x{addr:02X} {1 if pec else 0}")

    def pmbus_onoff_write(self, addr: int, value: int, pec: bool = True) -> None:
        """PMBUS:ONOFF <addr> <byte> <pec> → write ON_OFF_CONFIG"""
        self.command(f"PMBUS:ONOFF 0x{addr:02X} 0x{value & 0xFF:02X} {1 if pec else 0}")

    def pmbus_status_word(self, addr: int, pec: bool = True) -> int:
        """PMBUS:STATUS? <addr> <pec> → STATUS_WORD 16-bit value"""
        lines = self.query(f"PMBUS:STATUS? 0x{addr:02X} {1 if pec else 0}")
        return _parse_pmbus_ok_int(lines, expect_width=16)

    def pmbus_revision(self, addr: int, pec: bool = True) -> tuple[int, int, int]:
        """PMBUS:REV? <addr> <pec> → (raw_byte, part1_nibble, part2_nibble)。

        part1/part2 各代表 PMBus spec 的 Part I / Part II revision 子版本，
        例如 raw 0x33 = Part I rev 1.3 & Part II rev 1.3。
        """
        lines = self.query(f"PMBUS:REV? 0x{addr:02X} {1 if pec else 0}")
        if not lines:
            raise ScpiError("no response")
        text = lines[0].strip()
        if text.upper().startswith("ERR"):
            raise ScpiError(text)
        if not text.upper().startswith("OK"):
            raise ScpiError(f"unexpected: {text}")
        # OK 0xNN part1=1.X part2=1.Y
        parts = text.split()
        try:
            raw = int(parts[1], 16)
        except (IndexError, ValueError) as exc:
            raise ScpiError(f"bad rev response: {text!r}") from exc
        return raw, (raw >> 4) & 0x0F, raw & 0x0F

    def pmbus_mfr_revision(self, addr: int, pec: bool = True) -> bytes:
        """PMBUS:MFRREV? <addr> <pec> → 廠商 firmware revision 字串（raw bytes，UI 端負責轉 ASCII）。

        韌體已經處理過 block read 的 byte count，這裡只回 data bytes（去掉 count）。
        """
        lines = self.query(f"PMBUS:MFRREV? 0x{addr:02X} {1 if pec else 0}", idle_ms=200)
        if not lines:
            raise ScpiError("no response")
        text = lines[0].strip()
        if text.upper().startswith("ERR"):
            raise ScpiError(text)
        # 格式：OK <count> <hex bytes...>
        tokens = text.split()
        if len(tokens) < 2 or tokens[0].upper() != "OK":
            raise ScpiError(f"unexpected: {text}")
        try:
            count = int(tokens[1], 0)
        except ValueError as exc:
            raise ScpiError(f"bad count: {tokens[1]!r}") from exc
        data = bytearray()
        for tok in tokens[2:2 + count]:
            try:
                data.append(int(tok, 16))
            except ValueError as exc:
                raise ScpiError(f"bad hex: {tok!r}") from exc
        return bytes(data)

    def _pmbus_read_ok_byte(self, cmd: str) -> int:
        """共用：跑一條 PMBUS:xxx? 命令，期望回 `OK 0xNN`。"""
        lines = self.query(cmd)
        return _parse_pmbus_ok_int(lines, expect_width=8)

    def i2c_bus_idle(self) -> bool:
        """`I2C1:BUSIDLE?` → True 表示 SCL+SDA 都在 high（bus 在 idle）。"""
        lines = self.query("I2C1:BUSIDLE?")
        if not lines:
            raise ScpiError("no response to I2C1:BUSIDLE?")
        try:
            return bool(int(lines[0].strip()))
        except ValueError as exc:
            raise ScpiError(f"bad busidle response: {lines[0]!r}") from exc


def _pick_idn_line(lines: list[str]) -> Optional[str]:
    """從 *IDN? 回應的多行裡挑一行最像 IDN 的（容忍開頭丟 byte）。

    韌體標準 IDN 格式：`CommBench,STM32G071RB,v0.1`（3 欄、逗號分隔）。
    實務上 USB CDC 偶爾掉 byte，所以首欄可能是 `ommBench` / `mmBench` /
    `ComBench` / 甚至 `Bench` — 都要當合法 IDN 認得出來。

    比對優先順序（任一命中即取）：
      1. 首欄完全等於 'CommBench'
      2. 首欄包含 'CommBench'
      3. 首欄是 'CommBench' 的尾段子字串（容忍前面掉 1~6 byte），
         + 第二欄含 'STM32'（確保是 IDN 不是別的逗號分隔字串）
      4. 首欄含 'Bench' + 第二欄含 'STM32'（最寬鬆 fallback）
    都沒有就回 None。
    """
    vendor = EXPECTED_IDN_VENDOR        # 'CommBench'
    vendor_u = vendor.upper()           # 'COMMBENCH'

    tier_exact: Optional[str] = None
    tier_substr: Optional[str] = None
    tier_suffix: Optional[str] = None
    tier_loose: Optional[str] = None

    for ln in lines:
        if "," not in ln:
            continue
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 2:
            continue
        first_u = parts[0].upper()
        second_u = parts[1].upper() if len(parts) >= 2 else ""

        if first_u == vendor_u:
            tier_exact = ln
            break
        if vendor_u in first_u and tier_substr is None:
            tier_substr = ln
            continue
        # 是不是 'CommBench' 的尾段？（容忍最多丟 6 byte 開頭）
        if "STM32" in second_u:
            is_suffix = any(
                first_u == vendor_u[i:]
                for i in range(1, min(7, len(vendor_u)))
            )
            if is_suffix and tier_suffix is None:
                tier_suffix = ln
                continue
            if "BENCH" in first_u and tier_loose is None:
                tier_loose = ln
                continue

    return tier_exact or tier_substr or tier_suffix or tier_loose


def _parse_pmbus_ok_int(lines: list[str], expect_width: int) -> int:
    """PMBus `OK 0xNN` / `OK 0xNNNN` 回應解析。

    expect_width = 8 → 期望 byte (mask 0xFF)
    expect_width = 16 → 期望 word (mask 0xFFFF)
    韌體 ERR 行會 raise ScpiError。
    """
    if not lines:
        raise ScpiError("no response")
    text = lines[0].strip()
    if text.upper().startswith("ERR"):
        raise ScpiError(text)
    parts = text.split()
    if len(parts) < 2 or parts[0].upper() != "OK":
        raise ScpiError(f"unexpected: {text}")
    try:
        v = int(parts[1], 0)
    except ValueError as exc:
        raise ScpiError(f"bad value: {parts[1]!r}") from exc
    mask = (1 << expect_width) - 1
    return v & mask


def _parse_ok_hex(lines: list[str]) -> bytes:
    """韌體 READ / MEMREAD 回應格式：`OK XX YY ZZ ...`。"""
    if not lines:
        raise ScpiError("no response")
    text = lines[0].strip()
    if text.upper().startswith("ERR"):
        raise ScpiError("\n".join(lines))
    if not text.upper().startswith("OK"):
        raise ScpiError(f"unexpected response: {text}")
    tail = text[2:].strip()
    result = bytearray()
    for tok in tail.split():
        try:
            result.append(int(tok, 16))
        except ValueError as exc:
            raise ScpiError(f"bad hex byte {tok!r}") from exc
    return bytes(result)
