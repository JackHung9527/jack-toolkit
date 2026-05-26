"""縮減 Ftdi.PRODUCT_IDS 只剩 ft232h，避免碰到別顆 FT232R。"""
import os, sys, traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import libusb_package
import usb.backend.libusb1 as b1

_libusb_backend = b1.get_backend(find_library=libusb_package.find_library)

from pyftdi.ftdi import Ftdi
from pyftdi import usbtools as _ut

# 1. 強制 libusb1 backend
_ut.UsbTools._load_backend = classmethod(lambda cls: _libusb_backend)

# 2. 把 Ftdi 的 PID list 縮到只剩 232h (0x6014)，避免 enumerate 卡在其他 FTDI 裝置
print("Original Ftdi.PRODUCT_IDS:", Ftdi.PRODUCT_IDS)
Ftdi.PRODUCT_IDS = {Ftdi.FTDI_VENDOR: {'ft232h': 0x6014}}
print("Patched Ftdi.PRODUCT_IDS :", Ftdi.PRODUCT_IDS)

print()
print("[pyftdi list_devices]")
try:
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  -> {len(raw)} device(s)")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r}")
except Exception:
    traceback.print_exc()

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
    print("  GPIO closed OK")
except Exception:
    traceback.print_exc()
