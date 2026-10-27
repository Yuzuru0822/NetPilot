"""Shared paths and constants for NetPilot."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_EXE = ROOT / "core" / "sing-box-1.14.4-windows-amd64" / "sing-box.exe"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
SINGBOX_CONFIG = DATA_DIR / "singbox.json"
SETTINGS_FILE = DATA_DIR / "netpilot.json"
AGENT_PID_FILE = DATA_DIR / "agent.pid"
SINGBOX_PID_FILE = DATA_DIR / "singbox.pid"

AGENT_ADDR = "127.0.0.1"
AGENT_PORT = 19090
AGENT_BASE = f"http://{AGENT_ADDR}:{AGENT_PORT}"

CLASH_ADDR = "127.0.0.1:9090"
CLASH_BASE = f"http://{CLASH_ADDR}"
CLASH_SECRET = "netpilot-local-only"

for _d in (DATA_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
