"""CommBench doctor — 不開 UI，直接跑一輪 sanity test。

確認：(1) COM40 能不能開 (2) *IDN? 韌體有沒有回應 (3) PMBus 命令能不能跑、
分析儀能不能看到 trace。

用法：
    python doctor.py            # 預設位址 0x58、跑全部 PMBus 讀命令、PEC ON
    python doctor.py 0x40       # 換位址
    python doctor.py 0x58 nopec # 不帶 PEC

要先 **關掉 host UI** 才能跑（COM port 不能被兩個 process 同時佔）。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from host.core.scpi_client import ScpiClient, ScpiError, auto_detect_commbench


def banner(text: str) -> None:
    bar = "=" * (len(text) + 4)
    print()
    print(bar)
    print(f"  {text}  ")
    print(bar)


def try_op(name: str, fn):
    """跑一條操作，把例外 / 結果都印出來。"""
    print(f"\n[{name}]")
    try:
        result = fn()
    except ScpiError as exc:
        print(f"   ERR ScpiError: {exc}")
        return None
    except Exception as exc:
        print(f"   ERR {type(exc).__name__}: {exc}")
        return None
    print(f"   OK -> {result!r}")
    return result


def main() -> int:
    argv = sys.argv[1:]
    addr_str = argv[0] if argv else "0x58"
    pec_flag = True
    if len(argv) >= 2 and argv[1].lower() in ("nopec", "no", "0", "off"):
        pec_flag = False

    try:
        addr = int(addr_str, 0)
    except ValueError:
        print(f"bad addr: {addr_str!r}")
        return 2

    banner("Step 1: locate CommBench COM port")
    port = auto_detect_commbench(timeout_per_port_s=1.0)
    if port is None:
        print("找不到 CommBench 韌體。請確認：")
        print("  - NUCLEO-G071 已接 USB")
        print("  - host UI 已關閉 (COM port 不能被兩個 process 同時佔)")
        return 1
    print(f"   找到 CommBench in {port}")

    banner(f"Step 2: open {port} and *IDN?")
    cli = ScpiClient()
    try:
        cli.open(port)
    except Exception as exc:
        print(f"   開埠失敗: {exc}")
        return 1
    matched, idn = cli.verify_idn()
    print(f"   IDN: {idn!r}  (vendor match = {matched})")

    banner(f"Step 3: PMBus reads @ addr 0x{addr:02X}  PEC={pec_flag}")
    try_op("PMBUS:OP?",     lambda: f"0x{cli.pmbus_op_read(addr, pec=pec_flag):02X}")
    try_op("PMBUS:ONOFF?",  lambda: f"0x{cli.pmbus_onoff_read(addr, pec=pec_flag):02X}")
    try_op("PMBUS:STATUS?", lambda: f"0x{cli.pmbus_status_word(addr, pec=pec_flag):04X}")
    try_op("PMBUS:REV?",    lambda: cli.pmbus_revision(addr, pec=pec_flag))
    try_op("PMBUS:MFRREV?", lambda: cli.pmbus_mfr_revision(addr, pec=pec_flag))

    banner("Step 4: BUS state check")
    try_op("I2C1:BUSIDLE?", lambda: cli.i2c_bus_idle())

    cli.close()
    print("\n[done] 跑完。")
    print("如果以上任何 ERR 是 HAL=1 → I2C NACK / 卡死；")
    print("如果是 PEC mismatch → device 不認你的 PEC 計算；")
    print("如果完全 timeout / no response → 韌體沒處理該命令。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
