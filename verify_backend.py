# -*- coding: utf-8 -*-
"""Check the CBCT TMJ external Python environment."""
import sys
import struct

print("Python executable:", sys.executable)
print("Python version:", sys.version.replace("\\n", " "))
print("Architecture:", struct.calcsize("P") * 8, "bit")
if sys.version_info[:2] != (3, 10):
    raise SystemExit("ERROR: Please run this script with Python 3.10.")
if struct.calcsize("P") * 8 != 64:
    raise SystemExit("ERROR: A 64-bit Python environment is required.")

modules = [
    ("ants", "antspyx"),
    ("SimpleITK", "SimpleITK"),
    ("nibabel", "nibabel"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("pyvista", "pyvista"),
    ("vtk", "vtk"),
    ("trame", "trame"),
    ("trame_vtk", "trame-vtk"),
    ("trame_vuetify", "trame-vuetify"),
]
failed = []
for module_name, display_name in modules:
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "version not exposed")
        print("[OK] {}: {}".format(display_name, version))
    except Exception as exc:
        failed.append((display_name, repr(exc)))
        print("[FAIL] {}: {}".format(display_name, repr(exc)))

if failed:
    print("\\nEnvironment check failed:")
    for name, error in failed:
        print(" - {}: {}".format(name, error))
    raise SystemExit(1)
print("\\nAll required imports passed.")
