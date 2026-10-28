"""Build sing-box configuration from NetPilot settings.

Settings model (data/netpilot.json):
{
  "channels": {"direct": "以太网", "fastorange": "本地连接 2", ...},  # tag -> interface friendly name
  "default_channel": "direct",
  "process_rules": [{"process": "chrome.exe", "channel": "fastorange"}, ...],
  "domain_rules": [{"suffix": "google.com", "channel": "fastorange"}, ...],
  "dns": {"direct": "223.5.5.5", "fastorange": "8.8.8.8", "company": ""},
  "tun": {"interface_name": "NetPilot", "address": "172.19.0.1/30", "mtu": 1500}
}
"""
from __future__ import annotations

import json
from pathlib import Path

from . import paths

DEFAULT_SETTINGS: dict = {
    # Channel list is ordered; each channel has a stable internal `id` used in
    # sing-box config and rules, plus a user-editable display `name`.
    "channels": [
        {"id": "direct", "name": "公网直连", "interface": "以太网"},
        {"id": "fastorange", "name": "快橙·国际", "interface": "本地连接 2"},
        {"id": "company", "name": "公司内网", "interface": "本地连接"},
    ],
    "default_channel": "direct",
    # VPN clients' own tunnel traffic must always use the physical adapter,
    # otherwise the TUN can cause reconnect loops.
    "process_rules": [
        {"process": name, "channel": "direct", "enabled": True}
        for name in (
            "openvpn.exe", "FastOrange.exe",
            "SecoClient.exe", "SecoClientCS.exe", "SecoClientPromoteService.exe",
            "aTrustAgent.exe", "aTrustXtunnel.exe", "ECAgent.exe",
            "SangforPromoteService.exe", "SangforPW.exe",
        )
    ],
    "domain_rules": [],
    "dns": {"direct": "223.5.5.5", "fastorange": "8.8.8.8"},
    "tun": {"interface_name": "NetPilot", "address": "172.19.0.1/30", "mtu": 1500, "stack": "gvisor"},
}

# DoH certificates are issued to these names, not to the server IPs.
DOH_TLS_NAMES = {
    "223.5.5.5": "dns.alidns.com",
    "223.6.6.6": "dns.alidns.com",
    "8.8.8.8": "dns.google",
    "8.8.4.4": "dns.google",
    "1.1.1.1": "cloudflare-dns.com",
    "1.0.0.1": "cloudflare-dns.com",
    "119.29.29.29": "dns.pub",
}


def _make_dns_server(tag: str, conf, detour: str) -> dict:
    """DNS upstream. Defaults to DoH: UDP binding to VPN adapters is unreliable
    on this machine, while TCP/443 binding is proven to work."""
    if isinstance(conf, str):
        conf = {"server": conf}
    server = conf["server"]
    entry = {
        "type": conf.get("type", "https"),
        "tag": f"dns-{tag}",
        "server": server,
        "detour": detour,
    }
    if entry["type"] == "https":
        tls_name = conf.get("tls_name") or DOH_TLS_NAMES.get(server)
        if tls_name:
            entry["tls"] = {"server_name": tls_name}
    return entry


CHANNEL_NAMES = {"direct": "公网直连", "fastorange": "快橙·国际", "company": "公司内网"}


def _migrate_channels(raw) -> list[dict]:
    """Accept the legacy {tag: interface} mapping and upgrade it to the
    list-of-channels format, keeping ids stable so rules keep working."""
    if isinstance(raw, dict):
        return [
            {"id": tag, "name": CHANNEL_NAMES.get(tag, tag), "interface": iface}
            for tag, iface in raw.items()
        ]
    return raw


def load_settings() -> dict:
    if paths.SETTINGS_FILE.exists():
        with open(paths.SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(saved)
        merged["channels"] = _migrate_channels(merged["channels"])
        ids = [ch["id"] for ch in merged["channels"]]
        if merged.get("default_channel") not in ids:
            merged["default_channel"] = ids[0] if ids else "direct"
        return merged
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    with open(paths.SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def build_config(settings: dict) -> dict:
    channels: list[dict] = settings["channels"]
    channel_ids = [ch["id"] for ch in channels]
    default_channel: str = settings["default_channel"]
    process_rules: list[dict] = settings.get("process_rules", [])
    domain_rules: list[dict] = settings.get("domain_rules", [])
    dns_servers_conf: dict[str, str] = settings.get("dns", {})
    tun_conf: dict = settings.get("tun", DEFAULT_SETTINGS["tun"])

    dns_servers = []
    for tag, conf in dns_servers_conf.items():
        if not conf or tag not in channel_ids:
            continue
        dns_servers.append(_make_dns_server(tag, conf, tag))
    if not dns_servers:
        dns_servers.append({"type": "udp", "tag": "dns-direct", "server": "223.5.5.5"})

    def dns_tag(channel: str) -> str:
        return f"dns-{channel}" if any(s["tag"] == f"dns-{channel}" for s in dns_servers) else dns_servers[0]["tag"]

    outbounds = [
        {"type": "direct", "tag": ch["id"], "bind_interface": ch["interface"], "domain_resolver": dns_tag(ch["id"])}
        for ch in channels
    ]

    dns_rules = []
    for rule in process_rules:
        if not rule.get("enabled", True):
            continue
        if rule["channel"] == default_channel:
            continue  # no need to override DNS for apps on the default path
        dns_rules.append({
            "process_name": [rule["process"]],
            "action": "route",
            "server": dns_tag(rule["channel"]),
        })
    for rule in domain_rules:
        if not rule.get("enabled", True):
            continue
        dns_rules.append({
            "domain_suffix": [rule["suffix"]],
            "action": "route",
            "server": dns_tag(rule["channel"]),
        })

    route_rules: list[dict] = [
        {"action": "sniff"},
    ]
    for rule in process_rules:
        if not rule.get("enabled", True):
            continue
        route_rules.append({
            "process_name": [rule["process"]],
            "action": "route",
            "outbound": rule["channel"],
        })
    for rule in domain_rules:
        if not rule.get("enabled", True):
            continue
        route_rules.append({
            "domain_suffix": [rule["suffix"]],
            "action": "route",
            "outbound": rule["channel"],
        })
    # LAN/private addresses always use the physical interface unless a rule above matched.
    route_rules.append({"ip_is_private": True, "action": "route", "outbound": "direct"})

    return {
        "log": {"level": settings.get("log_level", "info"), "timestamp": True},
        "dns": {
            "servers": dns_servers,
            "rules": dns_rules,
            "final": dns_tag(default_channel),
            "strategy": "ipv4_only",
        },
        "inbounds": [{
            "type": "tun",
            "tag": "tun-in",
            "interface_name": tun_conf.get("interface_name", "NetPilot"),
            "address": [tun_conf.get("address", "172.19.0.1/30")],
            "mtu": tun_conf.get("mtu", 1500),
            "stack": tun_conf.get("stack", "gvisor"),
            "auto_route": True,
            "strict_route": False,
            # This machine's security driver filters port-53 packets on unknown
            # adapters, so TUN DNS hijack cannot work here. Leave system DNS on
            # its existing (working) paths; NetPilot only routes connections.
            "dns_mode": "disabled",
        }],
        "outbounds": outbounds,
        "route": {
            "rules": route_rules,
            "final": default_channel,
            "default_domain_resolver": dns_tag(default_channel),
        },
        "experimental": {
            "clash_api": {
                "external_controller": paths.CLASH_ADDR,
                "secret": paths.CLASH_SECRET,
            }
        },
    }


def generate(settings: dict | None = None) -> Path:
    settings = settings or load_settings()
    config = build_config(settings)
    with open(paths.SINGBOX_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return paths.SINGBOX_CONFIG


if __name__ == "__main__":
    print(generate())
