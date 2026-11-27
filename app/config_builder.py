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

# --- selector outbounds for hot-switching -----------------------------------
# The channel direct outbounds keep the plain channel id as their tag (the
# connections tab maps chains back to channels through it). Selector groups get
# an "np:" prefixed tag that can never collide with a channel id. Switching a
# selector via the Clash API (PUT /proxies/{tag}) re-routes traffic instantly
# without restarting the core, so "rule X now uses channel Y" and "the default
# channel changed" are hot-applicable; rule add/remove/enable still needs a
# full restart because route.rules themselves are static in sing-box.
FINAL_SELECTOR = "np:final"
PROCESS_RULE_PREFIX = "np:proc-"
SUFFIX_RULE_PREFIX = "np:suf-"


def process_rule_tag(index: int) -> str:
    return f"{PROCESS_RULE_PREFIX}{index}"


def suffix_rule_tag(index: int) -> str:
    return f"{SUFFIX_RULE_PREFIX}{index}"


def enabled_rules(rules: list[dict]) -> list[dict]:
    """Rules that make it into the config. Selector tags are indexed by the
    position within this filtered list, in both build_config and hot_patches."""
    return [r for r in rules if r.get("enabled", True)]


def _selector(tag: str, members: list[str], default: str) -> dict:
    return {
        "type": "selector",
        "tag": tag,
        "outbounds": list(members),
        "default": default if default in members else members[0],
        # A hot switch should take effect for existing connections too.
        "interrupt_exist_connections": True,
    }


def selection_only_change(old: dict, new: dict) -> bool:
    """Whether old->new only changes rule->channel targets or the default
    channel, i.e. everything the Clash API can hot-switch. Anything else
    (rules added/removed/enabled, channels edited, dns/tun/log changes)
    requires rebuilding the core."""
    if old.get("channels") != new.get("channels"):
        return False
    for section in ("dns", "tun", "log_level"):
        if old.get(section) != new.get(section):
            return False

    def sig(rules):
        return [(r.get("enabled", True), r.get("process") or r.get("suffix")) for r in rules]

    for key in ("process_rules", "domain_rules"):
        if sig(old.get(key, [])) != sig(new.get(key, [])):
            return False
    return True


def hot_patches(old: dict, new: dict) -> list[tuple[str, str]]:
    """(selector_tag, member_tag) pairs to switch via the Clash API. Only call
    this when selection_only_change(old, new) is True."""
    patches: list[tuple[str, str]] = []
    for key, prefix in (("process_rules", PROCESS_RULE_PREFIX),
                        ("domain_rules", SUFFIX_RULE_PREFIX)):
        old_on, new_on = enabled_rules(old[key]), enabled_rules(new[key])
        for i, (o, n) in enumerate(zip(old_on, new_on)):
            if o["channel"] != n["channel"]:
                patches.append((f"{prefix}{i}", n["channel"]))
    if old["default_channel"] != new["default_channel"]:
        patches.append((FINAL_SELECTOR, new["default_channel"]))
    return patches


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
    # Selector groups: one per enabled rule (so its target channel can be
    # hot-switched via the Clash API) plus one for the default channel.
    process_rules_on = enabled_rules(process_rules)
    domain_rules_on = enabled_rules(domain_rules)
    for i, rule in enumerate(process_rules_on):
        outbounds.append(_selector(process_rule_tag(i), channel_ids, rule["channel"]))
    for i, rule in enumerate(domain_rules_on):
        outbounds.append(_selector(suffix_rule_tag(i), channel_ids, rule["channel"]))
    outbounds.append(_selector(FINAL_SELECTOR, channel_ids, default_channel))

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
    for i, rule in enumerate(process_rules_on):
        route_rules.append({
            "process_name": [rule["process"]],
            "action": "route",
            "outbound": process_rule_tag(i),
        })
    for i, rule in enumerate(domain_rules_on):
        route_rules.append({
            "domain_suffix": [rule["suffix"]],
            "action": "route",
            "outbound": suffix_rule_tag(i),
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
            "final": FINAL_SELECTOR,
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
