"""Network adapter and process enumeration without WMI.

Get-NetAdapter hangs on this machine (VPN filter drivers), so everything
here uses psutil / IP Helper API backed calls instead.
"""
from __future__ import annotations

import locale
import re
import subprocess

import psutil

NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _ipconfig_text() -> str:
    out = subprocess.run(["ipconfig", "/all"], capture_output=True,
                         creationflags=NO_WINDOW)
    return out.stdout.decode(locale.getpreferredencoding(False), errors="replace")


def find_tap_adapter(ip_prefix: str) -> dict | None:
    """Locate a TAP-Windows V9 adapter carrying an IPv4 in the given prefix.

    Used to detect VPN state without UIA: FastOrange's tunnel always gets a
    192.168.255.x/30 address, SecoClient's gets 192.168.220.x. Driver
    descriptions are language independent, unlike adapter friendly names.
    """
    for block in re.split(r"\r?\n\r?\n", _ipconfig_text()):
        if "TAP-Windows Adapter V9" not in block or ip_prefix not in block:
            continue
        match = re.search(r"IPv4[^\d]*(\d+\.\d+\.\d+\.\d+)", block)
        if match:
            return {"ip": match.group(1)}
    return None


def process_exists(exe_name: str) -> bool:
    target = exe_name.lower()
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == target:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def list_adapters() -> list[dict]:
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    result = []
    for name, stat in stats.items():
        if name.startswith("Loopback") or name.lower() == "lo":
            continue
        ips = [a.address for a in addrs.get(name, []) if a.family.name == "AF_INET"]
        result.append({
            "name": name,
            "is_up": stat.isup,
            "ipv4": ips,
            "speed_mbps": stat.speed,
        })
    return sorted(result, key=lambda a: (not a["is_up"], a["name"]))


def list_processes() -> list[dict]:
    """Running processes with an executable path, deduplicated by exe."""
    seen: dict[str, dict] = {}
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info["name"] or ""
            exe = proc.info["exe"] or ""
            if not name.lower().endswith(".exe"):
                continue
            key = name.lower()
            if key not in seen:
                seen[key] = {"name": name, "exe": exe, "pids": []}
            seen[key]["pids"].append(proc.info["pid"])
            if not seen[key]["exe"] and exe:
                seen[key]["exe"] = exe
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(seen.values(), key=lambda p: p["name"].lower())


if __name__ == "__main__":
    import json
    print(json.dumps(list_adapters(), ensure_ascii=False, indent=2))
