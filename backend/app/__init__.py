"""ChemImage Converter backend."""
import sys
from pathlib import Path

# Minimal vendored subset of OpenNMT-py 2.2 (MIT) needed by MolScribe/RxnScribe;
# the full package pins torchtext, which no longer installs on modern Python.
_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
