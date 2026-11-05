# Functional regression tests for tray, connections, logs, and full exit.
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from app.gui import MainWindow

app = QApplication([])
w = MainWindow()

# Connections: with the core running and the tab selected, rows must populate.
w.core_running = True
w.tabs.setCurrentWidget(w.connections_tab)
w.refresh_connections()
deadline = time.time() + 12
while time.time() < deadline:
    app.processEvents()
    if w.conn_table.rowCount() > 0:
        break
    time.sleep(0.1)
assert w.conn_table.rowCount() > 0, "connections table stayed empty"
print("connections OK:", w.conn_table.rowCount())

# Logs: the logs tab must populate regardless of its position in the tab bar.
w.tabs.setCurrentWidget(w.logs_tab)
w.refresh_logs()
app.processEvents()
assert len(w.log_text.toPlainText()) > 100, "logs tab stayed empty"
print("logs OK:", len(w.log_text.toPlainText()))

# Tray restore: hidden -> visible and not minimized.
w.hide()
assert not w.isVisible()
w.show_main_window()
app.processEvents()
assert w.isVisible(), "show_main_window did not show the window"
assert not w.isMinimized(), "window remained minimized"
print("tray restore OK")

# Full exit: tray exit must call agent.shutdown, not just close the GUI.
called = {"shutdown": False}


class FakeAgent:
    def shutdown(self):
        called["shutdown"] = True
        return {"ok": True}


w.agent = FakeAgent()
w.quit_all()
deadline = time.time() + 5
while time.time() < deadline and not called["shutdown"]:
    app.processEvents()
    time.sleep(0.05)
assert called["shutdown"], "tray exit did not shut down the agent"
print("full exit OK")
print("ALL GUI FIX TESTS PASSED")
