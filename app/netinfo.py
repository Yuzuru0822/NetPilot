"""Network adapter and process enumeration without WMI.

Get-NetAdapter hangs on this machine (VPN filter drivers), so everything
here uses psutil / IP Helper API backed calls instead.
"""
from __future__ import annotations

import psutil


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
