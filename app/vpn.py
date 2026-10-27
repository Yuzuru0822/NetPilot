"""FastOrange / SecoClient automation wrappers (UIA via PowerShell scripts)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

FASTORANGE_SCRIPTS = Path(r"C:\Users\29455\.agents\skills\fastorange-control\scripts")
SECO_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run_ps1(path: Path, *args: str, timeout: int = 90) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *args],
        capture_output=True, text=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return (result.stdout or "") + (result.stderr or "")


def fastorange_state() -> dict:
    out = _run_ps1(FASTORANGE_SCRIPTS / "fastorange_state.ps1", timeout=40)
    state = "unknown"
    for line in out.splitlines():
        if line.startswith("STATE:"):
            state = line.split(":", 1)[1].strip()
    node = ""
    if "ServerNameText" in out:
        node = out.split("ServerNameText", 1)[1].splitlines()[0].strip(" :'")
    return {"state": state, "node": node, "raw": out}


def fastorange_connect() -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_connect.ps1")


def fastorange_disconnect() -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_disconnect.ps1")


def fastorange_select_server(name: str) -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_select_server.ps1", "-Name", name, timeout=120)


def seco_state() -> dict:
    out = _run_ps1(SECO_SCRIPTS / "seco_state.ps1", timeout=40)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                pass
    return {"state": "unknown", "raw": out}


def seco_connect() -> str:
    return _run_ps1(SECO_SCRIPTS / "seco_click.ps1", "-Action", "connect", timeout=40)


def seco_disconnect() -> str:
    return _run_ps1(SECO_SCRIPTS / "seco_click.ps1", "-Action", "disconnect", timeout=40)
