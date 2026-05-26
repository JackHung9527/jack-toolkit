"""終極方案: monkey-patch pyftdi._find_devices 用 libusb_package.find cached device。"""
import os, sys, traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import libusb_package
import usb.backend.libusb1 as b1

_libusb_backend = b1.get_backend(find_library=libusb_package.find_library)
_device_cache = {}


def _enum(vendor, product):
    key = (vendor, product)
    if key not in _device_cache:
        devs = set(usb.core.find(backend=_libusb_backend, find_all=True,
                                 idVendor=vendor, idProduct=product))
        _device_cache[key] = devs
    return _device_cache[key]


from pyftdi import usbtools as _ut

def _patched_find_devices(cls, vendor, product, nocache=False):
    return _enum(vendor, product)

def _patched_load_backend(cls):
    return _libusb_backend

_ut.UsbTools._find_devices = classmethod(_patched_find_devices)
_ut.UsbTools._load_backend = classmethod(_patched_load_backend)

print("Patched. Calling pyftdi list_devices...")
try:
    from pyftdi.ftdi import Ftdi
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  pyftdi -> {len(raw)} device(s)")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r}")
except Exception:
    traceback.print_exc()

print()
print("Trying GPIO open + read:")
try:
    from src.core.gpio_ctrl import GpioController
    g = GpioController()
    g.open("ftdi://ftdi:232h:FT96CS87/1", frequency_hz=1_000_000)
    for i in range(3):
        word = g.read_all()
        print(f"  read_all #{i+1} = 0x{word:04X}  ({word:016b})")
    g.close()
    print("  GPIO closed OK")
except Exception:
    traceback.print_exc()
