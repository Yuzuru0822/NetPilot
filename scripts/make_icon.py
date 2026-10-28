# Generate assets/netpilot.ico (blue circle with two-way arrows) via Qt + Pillow.
import io
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\NetPilot")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap

app = QGuiApplication([])
pix = QPixmap(256, 256)
pix.fill(Qt.transparent)
painter = QPainter(pix)
painter.setRenderHint(QPainter.Antialiasing)
painter.setBrush(QColor("#2563eb"))
painter.setPen(Qt.NoPen)
painter.drawEllipse(8, 8, 240, 240)
pen = QPen(QColor("white"))
pen.setWidth(18)
pen.setCapStyle(Qt.RoundCap)
pen.setJoinStyle(Qt.RoundJoin)
painter.setPen(pen)
painter.setBrush(Qt.NoBrush)
# right arrow (top), left arrow (bottom)
painter.drawLine(72, 96, 184, 96)
painter.drawLine(184, 96, 152, 64)
painter.drawLine(184, 96, 152, 128)
painter.drawLine(184, 160, 72, 160)
painter.drawLine(72, 160, 104, 128)
painter.drawLine(72, 160, 104, 192)
painter.end()

buffer = pix.toImage()
bits = buffer.bits()
raw = bytes(bits)
img = Image.frombytes("RGBA", (256, 256), raw, "raw", "BGRA")
os.makedirs(r"D:\NetPilot\assets", exist_ok=True)
img.save(r"D:\NetPilot\assets\netpilot.ico",
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(r"D:\NetPilot\assets\netpilot.png")
print("icon written to assets/netpilot.ico")
