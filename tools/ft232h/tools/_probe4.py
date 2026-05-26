"""warm-up 後再跑 pyftdi，看是否能 work。"""
import os, sys, traceback

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import usb.backend.libusb1 as b1
import libusb_package

# warm-up: 強制 libusb1 + libusb_package 跑一次
backend = b1.get_backend(find_library=libusb_package.find_library)
print(f"[warm-up] backend: {backend}")
warm = list(usb.core.find(backend=backend, find_all=True,
                          idVendor=0x0403, idProduct=0x6014))
print(f"[warm-up] found {len(warm)} device(s)")
for d in warm:
    try:
        sn = d.serial_number
        print(f"  warm sn={sn!r}")
    except Exception as ex:
        print(f"  warm open failed: {ex!r}")
    try:
        usb.util.dispose_resources(d)
    except Exception:
        pass

print()
print("[pyftdi] now call pyftdi list_devices:")
try:
    from pyftdi.ftdi import Ftdi
    raw = list(Ftdi.list_devices("ftdi://ftdi:232h/?"))
    print(f"  pyftdi -> {len(raw)} device(s)")
    for desc, iface in raw:
        print(f"    sn={desc.sn!r} desc={desc.description!r}")
except Exception:
    traceback.print_exc()
