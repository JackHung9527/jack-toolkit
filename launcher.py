"""jack-toolkit launcher (WIP placeholder).

目前還沒整合主視窗 + 選單切換，這個檔案先做一個簡單的 CLI 工具選單：
列出收錄的工具，讓使用者用數字選擇後 spawn 對應子程序。
之後會替換成 PySide6 主視窗 + tab/側邊欄切換。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"


TOOLS = [
    {
        "name": "Serial Port Tool",
        "dir":  "serial",
        "cmd":  [sys.executable, "main.py"],
        "desc": "COM port HEX/ASCII 收發、連續傳送、程式設計師計算機 (Qt6)",
    },
    {
        "name": "Network Scanner",
        "dir":  "netscan",
        "cmd":  [sys.executable, "network_scanner.py"],
        "desc": "IP range / port scan / ping monitor (tkinter)",
    },
    {
        "name": "FT232H Tester",
        "dir":  "ft232h",
        "cmd":  [sys.executable, "main.py"],
        "desc": "FT232H USB-to-GPIO/SPI/I2C 桌面測試 (tkinter)",
    },
]


def main() -> int:
    print("=" * 60)
    print(" jack-toolkit launcher")
    print("=" * 60)
    for i, t in enumerate(TOOLS, 1):
        print(f"  [{i}] {t['name']:<20s}  {t['desc']}")
    print("  [q] Quit")
    print()

    choice = input("選擇要啟動的工具: ").strip().lower()
    if choice in ("q", "quit", "exit", ""):
        return 0

    try:
        idx = int(choice) - 1
        tool = TOOLS[idx]
    except (ValueError, IndexError):
        print(f"無效選擇: {choice!r}")
        return 1

    cwd = TOOLS_DIR / tool["dir"]
    if not cwd.is_dir():
        print(f"找不到工具目錄: {cwd}")
        return 1

    print(f"啟動 {tool['name']} ({cwd}) ...")
    return subprocess.call(tool["cmd"], cwd=str(cwd))


if __name__ == "__main__":
    sys.exit(main())
