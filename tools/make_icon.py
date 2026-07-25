"""Generate ``installer/pktracker.ico`` from the app's painted brand mark.

Run once after changing the icon design::

    python tools/make_icon.py

Emits classic **uncompressed 32-bit BMP/DIB** icon entries (not PNG-compressed
ones): PyInstaller copies these verbatim into the ``.exe`` icon resource even
when it runs without Pillow (as it does in CI), whereas PNG-in-ICO entries can
be dropped — leaving the default floppy-disk/Python icon. Committed to the repo
so the build needs no extra step.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pk_tracker.ui.brand import paint_mark  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = Path(__file__).resolve().parent.parent / "installer" / "pktracker.ico"


def _render(n: int) -> QImage:
    img = QImage(n, n, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    paint_mark(p, n)
    p.end()
    return img


def _dib_bytes(n: int) -> bytes:
    """One icon image as a BMP/DIB: header + bottom-up BGRA + 1-bpp AND mask."""
    img = _render(n)
    # BITMAPINFOHEADER, with biHeight doubled to cover colour + mask planes.
    header = struct.pack("<IiiHHIIiiII", 40, n, n * 2, 1, 32, 0, 0, 0, 0, 0, 0)

    colour = bytearray()
    for y in range(n - 1, -1, -1):              # ICO stores rows bottom-up
        for x in range(n):
            c = img.pixel(x, y)                 # 0xAARRGGBB
            colour += bytes(((c) & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF, (c >> 24) & 0xFF))

    # 1-bit AND mask (1 = transparent), rows padded to a 32-bit boundary.
    row_bytes = ((n + 31) // 32) * 4
    mask = bytearray()
    for y in range(n - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(n):
            if ((img.pixel(x, y) >> 24) & 0xFF) < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        mask += row

    return header + bytes(colour) + bytes(mask)


def main() -> None:
    QApplication([])
    images = [(s, _dib_bytes(s)) for s in SIZES]
    out = struct.pack("<HHH", 0, 1, len(images))          # ICONDIR
    offset = 6 + 16 * len(images)
    blobs = b""
    for size, dib in images:
        dim = 0 if size >= 256 else size                  # 256 encoded as 0
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(dib), offset)
        offset += len(dib)
        blobs += dib
    OUT.write_bytes(out + blobs)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(images)} sizes, BMP/DIB)")


if __name__ == "__main__":
    main()
