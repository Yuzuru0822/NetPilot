# Offscreen functional test for dynamic channels (rename / add / delete).
import json
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\NetPilot")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config_builder import load_settings
from app.gui import MainWindow

QMessageBox.warning = staticmethod(lambda *a, **k: None)
app = QApplication([])
w = MainWindow()

ids = [r["id"] for r in w._channel_rows]
assert ids == ["direct", "fastorange", "company"], ids

# 1. Rename: dropdowns and rule combos must follow, ids stay stable.
row = next(r for r in w._channel_rows if r["id"] == "fastorange")
row["name_item"].setText("国际加速")
texts = [w.default_combo.itemText(i) for i in range(w.default_combo.count())]
assert "国际加速" in texts, texts
found = False
for r in range(w.process_table.rowCount()):
    combo = w.process_table.cellWidget(r, 2)
    if combo and "国际加速" in [combo.itemText(i) for i in range(combo.count())]:
        found = True
assert found, "rule combos did not update after rename"
assert w.default_combo.currentData() == "direct"
print("rename OK")

# 2. Add a new channel.
before = len(w._channel_rows)
w.add_channel()
assert len(w._channel_rows) == before + 1
new = w._channel_rows[-1]
assert w.default_combo.findData(new["id"]) >= 0
new["name_item"].setText("测试通道")
new["iface_combo"].setCurrentText("以太网")
print("add OK:", new["id"])

# 3. Apply: settings + generated sing-box config must include it.
w.apply_settings()
time.sleep(6)
s = load_settings()
names = {c["id"]: c["name"] for c in s["channels"]}
assert names.get("fastorange") == "国际加速", names
assert names.get(new["id"]) == "测试通道", names
conf = json.load(open(r"D:\NetPilot\data\singbox.json", encoding="utf-8"))
tags = [o["tag"] for o in conf["outbounds"]]
assert new["id"] in tags, tags
print("apply OK:", tags)

# 4. Delete the test channel and apply again.
w.delete_channel(new["id"])
assert all(r["id"] != new["id"] for r in w._channel_rows)
w.apply_settings()
time.sleep(5)
s = load_settings()
assert all(c["id"] != new["id"] for c in s["channels"])
print("delete OK")

# 5. Guard: a channel used by a rule must not be deletable.
used = any(
    (w.process_table.cellWidget(r, 2) and w.process_table.cellWidget(r, 2).currentData() == "fastorange")
    for r in range(w.process_table.rowCount())
)
if used:
    w.delete_channel("fastorange")
    assert any(r["id"] == "fastorange" for r in w._channel_rows), "used channel was deleted!"
    print("delete guard OK")

print("ALL GUI CHANNEL TESTS PASSED")
