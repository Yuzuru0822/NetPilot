"""FastOrange / SecoClient automation wrappers (UIA via PowerShell scripts).

State detection is two-layered: UIA reads the client window for details
(node name, login prompts), and a TAP-adapter check (192.168.255.x for
FastOrange, 192.168.220.x for SecoClient) provides a version/language-proof
fallback so state never degrades to "unknown" on other machines.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import paths
from .netinfo import find_tap_adapter, process_exists

FASTORANGE_SCRIPTS = paths.ROOT / "scripts" / "fastorange"
SECO_SCRIPTS = paths.ROOT / "scripts"


def _run_ps1(path: Path, *args: str, timeout: int = 90) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *args],
        capture_output=True, text=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return (result.stdout or "") + (result.stderr or "")


def fastorange_state() -> dict:
    result = {"state": "unknown", "node": "", "raw": ""}
    try:
        out = _run_ps1(FASTORANGE_SCRIPTS / "fastorange_state.ps1", timeout=40)
        result["raw"] = out
        for line in out.splitlines():
            if line.startswith("STATE:"):
                result["state"] = line.split(":", 1)[1].strip()
        if "ServerNameText" in out:
            result["node"] = out.split("ServerNameText", 1)[1].splitlines()[0].strip(" :'")
    except Exception as exc:
        result["raw"] = str(exc)
    # The adapter is authoritative when present; also the fallback when UIA
    # fails (missing client, different version, non-Chinese Windows).
    adapter = find_tap_adapter("192.168.255.")
    if adapter:
        result["state"] = "connected"
        result["ip"] = adapter["ip"]
    elif result["state"] in ("unknown", "", "not_running"):
        result["state"] = "disconnected" if process_exists("FastOrange.exe") else "not_running"
    return result


def fastorange_connect() -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_connect.ps1")


def fastorange_disconnect() -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_disconnect.ps1")


def fastorange_select_server(name: str) -> str:
    return _run_ps1(FASTORANGE_SCRIPTS / "fastorange_select_server.ps1", "-Name", name, timeout=120)


def seco_state() -> dict:
    result = {"state": "unknown", "raw": ""}
    try:
        out = _run_ps1(SECO_SCRIPTS / "seco_state.ps1", timeout=40)
        result["raw"] = out
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    result.update(json.loads(line))
                    break
                except ValueError:
                    pass
    except Exception as exc:
        result["raw"] = str(exc)
    if result["state"] in ("unknown", "", "not_running"):
        adapter = find_tap_adapter("192.168.220.")
        if adapter:
            result["state"] = "connected"
            result["ip"] = adapter["ip"]
        elif process_exists("SecoClient.exe"):
            result["state"] = "disconnected"
        else:
            result["state"] = "not_running"
    return result


def seco_connect() -> str:
    return _run_ps1(SECO_SCRIPTS / "seco_click.ps1", "-Action", "connect", timeout=40)


def seco_disconnect() -> str:
    return _run_ps1(SECO_SCRIPTS / "seco_click.ps1", "-Action", "disconnect", timeout=40)
