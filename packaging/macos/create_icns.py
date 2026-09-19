import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ICONSET_SIZES = (16, 32, 128, 256, 512)


def _render_png(svg_path: Path, destination: Path, size: int) -> None:
    renderer = QSvgRenderer(QByteArray(svg_path.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG icon source: {svg_path}")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(destination), "PNG"):
        raise RuntimeError(f"Unable to write PNG icon: {destination}")


def create_icns(svg_path: Path, output_path: Path) -> None:
    if shutil.which("iconutil") is None:
        raise RuntimeError("iconutil was not found. This script must run on macOS.")

    app = QGuiApplication.instance() or QGuiApplication(["create-icns"])
    _ = app
    iconset = output_path.with_suffix(".iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    for size in ICONSET_SIZES:
        base = iconset / f"icon_{size}x{size}.png"
        _render_png(svg_path, base, size)
        if size <= 512:
            retina = iconset / f"icon_{size}x{size}@2x.png"
            _render_png(svg_path, retina, size * 2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["iconutil", "--convert", "icns", str(iconset), "--output", str(output_path)],
        check=True,
    )
    shutil.rmtree(iconset, ignore_errors=True)


if __name__ == "__main__":
    create_icns(Path(sys.argv[1]), Path(sys.argv[2]))
