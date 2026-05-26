"""diagnostic probe: 模擬 GUI 啟動流程，找出 list_devices 被吞掉的真實 exception。"""
import os
import sys
import traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

print("python:", sys.executable)
print("cwd   :", os.getcwd())
print()

# 1. main.py 的 backend setup
from main import _setup_libusb_backend
_setup_libusb_backend()
print("[step1] _setup_libusb_backend OK")

# 2. 我的 wrapper
from src.core.device import list_devices
try:
    devs = list_devices()
    print(f"[step2] list_devices() -> {len(devs)} device(s)")
    for d in devs:
        print(f"  {d.display}")
except Exception:
    print("[step2] list_devices raised:")
    traceback.print_exc()

# 3. 原始 pyftdi API（看是否 wrapper 吞 exception）
from pyftdi.ftdi import Ftdi
print()
print("[step3] raw Ftdi.list_devices('ftdi://ftdi:232h/?'):")
try:
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  raw -> {len(raw)} entries")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r} iface={iface}")
except Exception:
    traceback.print_exc()

# 4. 不加 query string 試一次（pyftdi 0.57 改過 API）
print()
print("[step4] Ftdi.list_devices() with no arg:")
try:
    raw2 = list(Ftdi.list_devices())
    print(f"  raw2 -> {len(raw2)} entries")
    for desc, iface in raw2:
        print(f"    sn={desc.sn!r} desc={desc.description!r} iface={iface}")
except Exception:
    traceback.print_exc()
