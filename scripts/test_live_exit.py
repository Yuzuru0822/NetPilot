# Live desktop test of show_main_window and quit_all using the real GUI code.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.gui import MainWindow

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
window = MainWindow()
window.show()
QTimer.singleShot(1500, window.hide)
QTimer.singleShot(2500, window.show_main_window)
QTimer.singleShot(4500, window.quit_all)
app.exec()
