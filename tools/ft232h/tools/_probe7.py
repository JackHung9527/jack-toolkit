"""monkey-patch pyftdi UsbTools._load_backend 強制注入 libusb_package backend。"""
import os, sys, traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.backend.libusb1 as b1
import libusb_package

# 預先拿到正確的 backend (透過 libusb_package.find_library)
_backend = b1.get_backend(find_library=libusb_package.find_library)
print(f"libusb_package backend: {_backend}")

# Monkey-patch pyftdi
from pyftdi import usbtools as _ut

def _patched_load_backend(cls):
    return _backend

_ut.UsbTools._load_backend = classmethod(_patched_load_backend)
print("pyftdi UsbTools._load_backend patched")

# 試 pyftdi list_devices
print()
print("[pyftdi list_devices after patch]")
try:
    from pyftdi.ftdi import Ftdi
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  -> {len(raw)} device(s)")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r}")
except Exception:
    traceback.print_exc()

# 真正試 GPIO open + read
print()
print("[GPIO open + read]")
try:
    from src.core.gpio_ctrl import GpioController
    g = GpioController()
    g.open("ftdi://ftdi:232h:FT96CS87/1", frequency_hz=1_000_000)
    for i in range(3):
        word = g.read_all()
        print(f"  read_all #{i+1} = 0x{word:04X}")
    g.close()
    print("  closed OK")
except Exception:
    traceback.print_exc()
