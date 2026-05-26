"""驗證: backend = libusb1, GPIO read 不再 timeout。"""
import os
import sys

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

# 同 main.py 的步驟
from main import _setup_libusb_backend
_setup_libusb_backend()

import ctypes.util
print("[after setup] find_library('usb-1.0')    =", ctypes.util.find_library("usb-1.0"))
print("[after setup] find_library('libusb-1.0') =", ctypes.util.find_library("libusb-1.0"))

import usb.backend.libusb1 as b1
import usb.backend.libusb0 as b0
print("[after setup] libusb1 backend:", b1.get_backend())
print("[after setup] libusb0 backend:", b0.get_backend())
print()

from src.core.device import list_devices
devs = list_devices()
print(f"list_devices -> {len(devs)} device(s)")
for d in devs:
    print(f"  {d.display}")

if not devs:
    print("沒找到裝置，後面跳過")
    sys.exit(1)

url = devs[0].url
print()
print(f"--- GPIO open / read 測試 ({url}) ---")
from src.core.gpio_ctrl import GpioController, PIN_NAMES
g = GpioController()
try:
    g.open(url, frequency_hz=1_000_000)
    print("GPIO opened OK")
    for i in range(3):
        word = g.read_all()
        print(f"  read_all() #{i+1} = 0x{word:04X}  ({bin(word)})")
finally:
    g.close()
    print("GPIO closed")
