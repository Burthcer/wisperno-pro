"""
Draws the Wisperno Pro logo and writes every icon file the app and installer use:

  assets/icon.svg, assets/icon.png, assets/icon.ico
  assets/icons/wisperno.png, assets/icons/wisperno.ico   (what the app, tray and installer load)

The mark is the pill's live waveform in the site's near-black, on an orange
rounded tile (devbhamaria.com palette: #FF5714 / #0C0C0B).

Run: python scripts/make_icon.py
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

BASE_DIR = Path(__file__).resolve().parent.parent

ORANGE_TOP, ORANGE_BOTTOM, INK = "#FF7A3D", "#FF5714", "#0C0C0B"
# Geometry in a 256 x 256 box.
TILE = (12, 12, 232, 232, 58)             # x, y, w, h, corner radius
BAR_W, BAR_GAP = 26, 12
BAR_HEIGHTS = (66, 116, 162, 98, 58)       # a voice-like waveform, tallest bar just left of centre
# With the "PRO" tag (what tells this app apart from the original Wisperno) the
# waveform shrinks and moves up; the tag is dropped below BADGE_MIN_PX where it can't be read.
BADGE_SCALE, BADGE_BARS_CY = 0.74, 106
BADGE = (74, 172, 108, 44)                  # x, y, w, h of the dark tag
BADGE_MIN_PX = 48


_BADGE_FAMILY = "Inter Tight"


def _load_badge_font() -> None:
    """The headless renderer has no system fonts to speak of, so use the app's own bundled face."""
    from PySide6.QtGui import QFontDatabase

    families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(BASE_DIR / "assets" / "fonts" / "InterTight-Variable.ttf")))
    if families:
        globals()["_BADGE_FAMILY"] = families[0]


def draw(size: int, badge: bool = True) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 256.0, size / 256.0)
    x, y, w, h, r = TILE
    grad = QLinearGradient(0, y, 0, y + h)
    grad.setColorAt(0, QColor(ORANGE_TOP))
    grad.setColorAt(1, QColor(ORANGE_BOTTOM))
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(x, y, w, h), r, r)
    p.fillPath(tile, grad)
    k = BADGE_SCALE if badge else 1.0
    cy = BADGE_BARS_CY if badge else 128
    bw, gap = BAR_W * k, BAR_GAP * k
    total = len(BAR_HEIGHTS) * bw + (len(BAR_HEIGHTS) - 1) * gap
    bx = (256 - total) / 2.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(INK))
    for bar_h in BAR_HEIGHTS:
        p.drawRoundedRect(QRectF(bx, cy - bar_h * k / 2.0, bw, bar_h * k), bw / 2.0, bw / 2.0)
        bx += bw + gap
    if badge:
        tx, ty, tw, th = BADGE
        p.drawRoundedRect(QRectF(tx, ty, tw, th), th / 2.0, th / 2.0)
        font = QFont(_BADGE_FAMILY)
        font.setWeight(QFont.Weight.Bold)
        font.setPixelSize(30)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        p.setFont(font)
        p.setPen(QColor(ORANGE_BOTTOM))
        p.drawText(QRectF(tx, ty, tw, th), Qt.AlignmentFlag.AlignCenter, "PRO")
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, sizes=(16, 32, 48, 64, 128, 256)) -> None:
    """A multi-size .ico whose entries are PNGs (supported since Windows Vista)."""
    entries = []
    for s in sizes:
        # Draw big and shrink smoothly: crisper than drawing straight at 16 px.
        img = draw(s * 4, badge=s >= BADGE_MIN_PX).scaled(s, s, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        entries.append((s, png_bytes(img)))
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory, blobs = b"", b""
    for s, data in entries:
        directory += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(header + directory + blobs)


def svg() -> str:
    x, y, w, h, r = TILE
    k, cy = BADGE_SCALE, BADGE_BARS_CY
    bw, gap = BAR_W * k, BAR_GAP * k
    total = len(BAR_HEIGHTS) * bw + (len(BAR_HEIGHTS) - 1) * gap
    bx = (256 - total) / 2.0
    parts = []
    for bar_h in BAR_HEIGHTS:
        parts.append(f'  <rect x="{bx:.1f}" y="{cy - bar_h * k / 2:.1f}" width="{bw:.1f}" height="{bar_h * k:.1f}" rx="{bw / 2:.1f}" fill="{INK}"/>')
        bx += bw + gap
    tx, ty, tw, th = BADGE
    parts.append(f'  <rect x="{tx}" y="{ty}" width="{tw}" height="{th}" rx="{th // 2}" fill="{INK}"/>')
    parts.append(f'  <text x="{tx + tw / 2:g}" y="{ty + 31}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
                 f'font-size="30" font-weight="bold" letter-spacing="2.5" fill="{ORANGE_BOTTOM}">PRO</text>')
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
        '  <defs><linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ORANGE_TOP}"/><stop offset="1" stop-color="{ORANGE_BOTTOM}"/></linearGradient></defs>',
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="url(#tile)"/>',
        *parts,
        '</svg>',
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    _load_badge_font()
    png = draw(1024).scaled(512, 512, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    (BASE_DIR / "assets" / "icons").mkdir(parents=True, exist_ok=True)
    for folder, png_name, ico_name in (("assets", "icon.png", "icon.ico"), ("assets/icons", "wisperno.png", "wisperno.ico")):
        png.save(str(BASE_DIR / folder / png_name))
        write_ico(BASE_DIR / folder / ico_name)
    (BASE_DIR / "assets" / "icon.svg").write_text(svg(), encoding="utf-8")
    print("icons written")


if __name__ == "__main__":
    main()
