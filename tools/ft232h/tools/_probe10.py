"""精確複製 probe6 流程 (backend.enumerate_devices) 作為 cache，不用 usb.core.find。"""
import os, sys, traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import libusb_package
import usb.backend.libusb1 as b1

_libusb_backend = b1.get_backend(find_library=libusb_package.find_library)
_device_cache = None  # 全 process 只 enumerate 一次

def _enumerate_once():
    global _device_cache
    if _device_cache is None:
        # 用 probe6 完全相同的流程
        out = []
        for raw_dev in _libusb_backend.enumerate_devices():
            d = usb.core.Device(raw_dev, _libusb_backend)
            out.append(d)
        _device_cache = out
        print(f"[enumerate once] cached {len(out)} total USB device(s)")
    return _device_cache


from pyftdi import usbtools as _ut

def _patched_find_devices(cls, vendor, product, nocache=False):
    all_devs = _enumerate_once()
    matched = set()
    for d in all_devs:
        if d.idVendor == vendor and d.idProduct == product:
            matched.add(d)
    return matched

def _patched_load_backend(cls):
    return _libusb_backend

_ut.UsbTools._find_devices = classmethod(_patched_find_devices)
_ut.UsbTools._load_backend = classmethod(_patched_load_backend)

print("Calling pyftdi list_devices after patch:")
try:
    from pyftdi.ftdi import Ftdi
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  -> {len(raw)} device(s)")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r}")
except Exception:
    traceback.print_exc()

print()
print("GPIO test:")
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
