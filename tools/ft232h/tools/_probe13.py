"""把 Ftdi.PRODUCT_IDS 縮成只剩 PID=0x6014 的 alias，
其他 FTDI 裝置 (FT232R 6001 etc) 就不會被 enumerate 卡住。"""
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

_ut.UsbTools._load_backend = classmethod(lambda cls: _libusb_backend)

# 保留所有指向 0x6014 的 alias name (232h, ft232h)
_orig_pids = Ftdi.PRODUCT_IDS[Ftdi.FTDI_VENDOR]
Ftdi.PRODUCT_IDS = {
    Ftdi.FTDI_VENDOR: {name: pid for name, pid in _orig_pids.items() if pid == 0x6014}
}
print("Patched PRODUCT_IDS:", Ftdi.PRODUCT_IDS)

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
