"""比對 probe6 流程 vs pyftdi _find_devices，找出 device 物件差異。"""
import os, sys

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import usb.backend.libusb1 as b1
import libusb_package

backend = b1.get_backend(find_library=libusb_package.find_library)

print("=== probe6 style ===")
devs_a = []
for raw in backend.enumerate_devices():
    d = usb.core.Device(raw, backend)
    if d.idVendor == 0x0403 and d.idProduct == 0x6014:
        devs_a.append(d)
        print(f"  raw id={id(raw):x} type={type(raw).__name__}")
        print(f"  Device id={id(d):x}")

print()
print("=== pyftdi _find_devices style (run in SAME process AFTER probe6 style) ===")
from pyftdi import usbtools as _ut

# Monkey-patch _load_backend to use our backend
_ut.UsbTools.UsbDevices.clear()  # clear cache
_ut.UsbTools._load_backend = classmethod(lambda cls: backend)

devs_b = _ut.UsbTools._find_devices(0x0403, 0x6014, nocache=True)
print(f"  pyftdi returned {len(devs_b)} device(s)")
for d in devs_b:
    print(f"  Device id={id(d):x}  raw id={id(d._ctx.dev):x} type={type(d._ctx.dev).__name__}")

print()
print("=== now try to read sn from each ===")
for d in devs_a:
    try:
        sn = d.serial_number
        print(f"  devs_a sn={sn!r}")
    except Exception as ex:
        print(f"  devs_a FAIL {ex!r}")
for d in devs_b:
    try:
        sn = d.serial_number
        print(f"  devs_b sn={sn!r}")
    except Exception as ex:
        print(f"  devs_b FAIL {ex!r}")
