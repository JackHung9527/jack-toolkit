"""精細對比: pyftdi enumerate 拿到的 device 跟 usb.core.find 拿到的 device 是否相同。"""
import os, sys, struct
import platform

print(f"python: {sys.version}")
print(f"arch:   {platform.architecture()}")
print()

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import usb.util
import usb.backend.libusb1 as b1
import libusb_package

# Force libusb1 backend with libusb_package
backend = b1.get_backend(find_library=libusb_package.find_library)
print(f"backend: {backend}")
print(f"backend._lib path: ", b1._lib)
print()

# Method 1: usb.core.find with vendor/product filter (warm-up path)
print("[M1] usb.core.find(idVendor=0x0403, idProduct=0x6014, find_all=True, backend=backend):")
m1 = list(usb.core.find(backend=backend, find_all=True,
                         idVendor=0x0403, idProduct=0x6014))
for i, d in enumerate(m1):
    print(f"  m1[{i}] bus={d.bus} addr={d.address} idVendor={d.idVendor:04x} idProduct={d.idProduct:04x}")
    print(f"        port_number={getattr(d, 'port_number', '?')} backend={type(d._ctx.backend).__module__}")
    print(f"        _ctx.dev type: {type(d._ctx.dev).__name__}")

# Method 2: backend.enumerate_devices() then filter (pyftdi path)
print()
print("[M2] backend.enumerate_devices() then filter by VID/PID:")
m2 = []
for raw_dev in backend.enumerate_devices():
    d = usb.core.Device(raw_dev, backend)
    if d.idVendor == 0x0403 and d.idProduct == 0x6014:
        m2.append(d)
        print(f"  m2[{len(m2)-1}] bus={d.bus} addr={d.address}")
        print(f"        _ctx.dev type: {type(d._ctx.dev).__name__}")

# Try open both
print()
print("[try M1 open]")
for d in m1:
    try:
        sn = d.serial_number
        print(f"  OK sn={sn!r}")
    except Exception as ex:
        print(f"  FAIL {ex!r}")

print()
print("[try M2 open]")
for d in m2:
    try:
        sn = d.serial_number
        print(f"  OK sn={sn!r}")
    except Exception as ex:
        print(f"  FAIL {ex!r}")
