"""Generate ``installer/pktracker.ico`` from the app's painted icon.

Run once after changing the icon design::

    python tools/make_icon.py

It renders the shared :func:`pk_tracker.ui.tray._paint_icon` mark at several
sizes and assembles a multi-resolution, PNG-compressed ``.ico`` (supported by
Windows Vista+). The file is committed so the CI build embeds it into the
``.exe`` without any extra build step.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, Qt  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pk_tracker.ui.tray import _paint_icon  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = Path(__file__).resolve().parent.parent / "installer" / "pktracker.ico"


def _png_bytes(size: int) -> bytes:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    _paint_icon(p, size)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> None:
    QApplication([])
    images = [(s, _png_bytes(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    entries = b""
    data = b""
    offset = 6 + 16 * len(images)
    for size, png in images:
        dim = 0 if size >= 256 else size            # 256 is encoded as 0
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        data += png
    OUT.write_bytes(header + entries + data)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(images)} sizes)")


if __name__ == "__main__":
    main()
