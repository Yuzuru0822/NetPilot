# Render README screenshots from the real GUI with demo data (no live config touched).
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

import app.gui as guimod
from app.config_builder import load_settings

settings = load_settings()
settings["channels"] = [
    {"id": "direct", "name": "公网直连", "interface": "以太网"},
    {"id": "intl", "name": "国际通道", "interface": "本地连接 2"},
    {"id": "wifi", "name": "备用通道", "interface": "WLAN"},
]
settings["default_channel"] = "direct"
settings["process_rules"] = [
    {"process": "chrome.exe", "channel": "intl", "enabled": True},
    {"process": "msedge.exe", "channel": "direct", "enabled": True},
    {"process": "idea64.exe", "channel": "wifi", "enabled": True},
    {"process": "curl.exe", "channel": "intl", "enabled": True},
]
settings["domain_rules"] = [
    {"suffix": "google.com", "channel": "intl", "enabled": True},
]


class FakeAgent:
    def status(self):
        return {"agent_pid": 40000, "singbox_running": True, "singbox_starting": False,
                "singbox_pid": 32324, "singbox_started_at": time.time(), "config_exists": True}

    def __getattr__(self, name):
        return lambda *a, **k: {"ok": True, "message": ""}


class FakeClash:
    def connections(self):
        rows = [
            ("chrome.exe", "www.google.com", "intl", 3_200_000, 120_000, "ProcessName", "chrome.exe"),
            ("curl.exe", "ipinfo.io", "intl", 820_000, 31_000, "ProcessName", "curl.exe"),
            ("msedge.exe", "cn.bing.com", "direct", 1_600_000, 96_000, "final", ""),
            ("idea64.exe", "172.168.63.103", "wifi", 480_000, 210_000, "ProcessName", "idea64.exe"),
            ("weixin.exe", "14.116.242.250", "direct", 260_000, 40_000, "final", ""),
        ]
        result = []
        for i, (proc, host, channel, down, up, rule, payload) in enumerate(rows):
            result.append({
                "id": f"demo-{i}",
                "metadata": {"process": proc, "host": host, "destinationPort": 443,
                             "destinationIP": host},
                "chains": [channel, "tun-in"],
                "rule": rule, "rulePayload": payload,
                "upload": up, "download": down,
            })
        return result


guimod.load_settings = lambda: settings
guimod.AgentClient = lambda: FakeAgent()
guimod.ClashClient = lambda: FakeClash()
guimod.MainWindow.refresh_adapters = lambda self: None

app = QApplication([])
window = guimod.MainWindow()
window.status_timer.stop()
window.conn_timer.stop()
window.log_timer.stop()
window.refresh_logs = lambda: None

# Channel status column for a clean demo picture.
for i, row in enumerate(window._channel_rows):
    window.channel_table.setItem(i, 2, window._channel_rows[i]["name_item"].__class__("🟢 在线"))

OUT.mkdir(parents=True, exist_ok=True)

pages = [
    (0, "rules"),
    (1, "connections"),
    (2, "logs"),
]

# Connections with plausible rates (pre-populated previous snapshot).
now = time.time()
for conn in window.clash.connections():
    cid = conn["id"]
    window._prev_conns[cid] = (conn["upload"] - 6_000, conn["download"] - 900_000, now - 2.0)

log_lines = """+0800 2026-11-05 10:00:00 INFO inbound/tun[tun-in]: started at NetPilot
+0800 2026-11-05 10:00:00 INFO network: updated default interface WLAN, index 14
+0800 2026-11-05 10:00:01 INFO clash-api: restful api listening at 127.0.0.1:9090
+0800 2026-11-05 10:00:01 INFO sing-box started (4.2s)
+0800 2026-11-05 10:00:02 INFO [4123456789 0ms] inbound/tun[tun-in]: inbound connection from 172.19.0.1:52310
+0800 2026-11-05 10:00:02 INFO [4123456789 1ms] inbound/tun[tun-in]: inbound connection to 142.250.66.78:443
+0800 2026-11-05 10:00:02 INFO [4123456789 1ms] router: found process path: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
+0800 2026-11-05 10:00:02 INFO [4123456789 2ms] router: match process_name=chrome.exe => route(intl)
+0800 2026-11-05 10:00:02 INFO [4123456789 3ms] outbound/direct[intl]: outbound connection to 142.250.66.78:443
+0800 2026-11-05 10:00:05 INFO [2987311212 0ms] inbound/tun[tun-in]: inbound connection to 117.186.232.18:443
+0800 2026-11-05 10:00:05 INFO [2987311212 1ms] router: found process path: C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe
+0800 2026-11-05 10:00:05 INFO [2987311212 1ms] router: match process_name=msedge.exe => route(direct)
+0800 2026-11-05 10:00:05 INFO [2987311212 2ms] outbound/direct[direct]: outbound connection to 117.186.232.18:443"""

for index, name in pages:
    window.tabs.setCurrentIndex(index)
    if index == 1:
        window._update_connections(window.clash.connections())
    if index == 2:
        window.log_text.setPlainText(log_lines)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    image = window.grab()
    image.save(str(OUT / f"{name}.png"))
    print("saved", OUT / f"{name}.png", image.width(), "x", image.height())
