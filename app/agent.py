"""NetPilot privileged agent.

Runs elevated (administrator). Owns the sing-box core process and all
operations that require admin rights. Controlled via loopback-only HTTP
with a per-install token, so the GUI and CLI never need elevation.

    python -m app.agent        # from the NetPilot root, as administrator
"""
from __future__ import annotations

import atexit
import ipaddress
import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import paths

LOG = logging.getLogger("netpilot.agent")
AUTOSTART_FILE = paths.DATA_DIR / "autostart"
NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _run(cmd, **kwargs):
    """subprocess.run that never flashes a console window on the user's desktop."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


def _tun_gateway() -> str:
    """TUN gateway is the second host of the configured /30 (172.19.0.1/30 -> .2)."""
    try:
        settings = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
        prefix = settings.get("tun", {}).get("address", "172.19.0.1/30")
        hosts = list(ipaddress.ip_network(prefix, strict=False).hosts())
        return str(hosts[1]) if len(hosts) >= 2 else "172.19.0.2"
    except Exception:
        return "172.19.0.2"


def apply_route_fix() -> str:
    """Make the TUN win over full-tunnel VPNs that push 0.0.0.0/1 + 128.0.0.0/1.

    Windows prefers the longest prefix, so a /0 default route alone loses to
    OpenVPN-style /1 routes. We add our own /1 routes via the TUN gateway with
    metric 0, beating the VPN's (metric 3) while leaving them in place: traffic
    sing-box explicitly binds to the VPN adapter still needs those /1 routes.
    """
    gateway = _tun_gateway()
    messages = []
    for network in ("0.0.0.0", "128.0.0.0"):
        _run(["route", "delete", network, "mask", "128.0.0.0", gateway],
                       capture_output=True)
        out = _run(["route", "add", network, "mask", "128.0.0.0", gateway, "metric", "1"],
                             capture_output=True, text=True)
        ok = out.returncode == 0
        messages.append(f"{network}/1 via {gateway}: {'ok' if ok else out.stdout + out.stderr}")
        LOG.info("route fix %s", messages[-1])
    return "\n".join(messages)


def remove_route_fix() -> None:
    gateway = _tun_gateway()
    for network in ("0.0.0.0", "128.0.0.0"):
        _run(["route", "delete", network, "mask", "128.0.0.0", gateway],
                       capture_output=True)


def setup_logging() -> None:
    handler = logging.FileHandler(paths.LOG_DIR / "agent.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)


class SingBox:
    """Owns the sing-box child process."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.started_at: float | None = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> tuple[bool, str]:
        with self.lock:
            if self.running():
                return True, "already running"
            if not paths.CORE_EXE.exists():
                return False, f"core not found: {paths.CORE_EXE}"
            if not paths.SINGBOX_CONFIG.exists():
                return False, "config not generated yet"
            log_file = open(paths.LOG_DIR / "singbox.log", "w", encoding="utf-8")
            try:
                self.proc = subprocess.Popen(
                    [str(paths.CORE_EXE), "run", "-c", str(paths.SINGBOX_CONFIG)],
                    cwd=str(paths.CORE_EXE.parent),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as exc:
                log_file.close()
                return False, f"spawn failed: {exc}"
            self.started_at = time.time()
            paths.SINGBOX_PID_FILE.write_text(str(self.proc.pid))
            LOG.info("sing-box started pid=%s", self.proc.pid)
            time.sleep(3)
            if self.proc.poll() is not None:
                return False, "exited at startup:\n" + tail_singbox_log(40)
            fix_msg = apply_route_fix()
            return True, f"running pid={self.proc.pid}\nroute fix:\n{fix_msg}"

    def stop(self) -> tuple[bool, str]:
        with self.lock:
            if not self.running():
                return True, "not running"
            pid = self.proc.pid
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
            self.proc = None
            LOG.info("sing-box stopped pid=%s", pid)
            remove_route_fix()
            return True, "stopped"

    def restart(self) -> tuple[bool, str]:
        self.stop()
        return self.start()


CORE = SingBox()


def tail_singbox_log(n: int = 40) -> str:
    log_path = paths.LOG_DIR / "singbox.log"
    if not log_path.exists():
        return "(no log)"
    try:
        return "".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-n:])
    except OSError as exc:
        return f"(log read failed: {exc})"


def agent_token() -> str:
    token_file = paths.DATA_DIR / "agent.token"
    if not token_file.exists():
        token_file.write_text(secrets.token_hex(16))
    return token_file.read_text().strip()


def status() -> dict:
    return {
        "agent_pid": os.getpid(),
        "singbox_running": CORE.running(),
        "singbox_pid": CORE.proc.pid if CORE.running() else None,
        "singbox_started_at": CORE.started_at,
        "config_exists": paths.SINGBOX_CONFIG.exists(),
        "core_exe": str(paths.CORE_EXE),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "NetPilotAgent/0.1"

    def log_message(self, fmt, *args):  # route http logs into our file
        LOG.info("http " + fmt, *args)

    def _send(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return self.headers.get("X-NetPilot-Token") == TOKEN

    def do_GET(self) -> None:
        if not self._authorized():
            self._send({"error": "unauthorized"}, 401)
            return
        if self.path == "/status":
            self._send(status())
        elif self.path == "/routes":
            out = _run(["route", "print", "-4"], capture_output=True, text=True)
            self._send({"routes": out.stdout})
        elif self.path.startswith("/singbox-log"):
            self._send({"log": tail_singbox_log(80)})
        else:
            self._send({"error": "unknown endpoint"}, 404)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send({"error": "unauthorized"}, 401)
            return
        if self.path == "/start":
            ok, msg = CORE.start()
            if ok:
                AUTOSTART_FILE.touch()
            self._send({"ok": ok, "message": msg}, 200 if ok else 500)
        elif self.path == "/stop":
            AUTOSTART_FILE.unlink(missing_ok=True)
            ok, msg = CORE.stop()
            self._send({"ok": ok, "message": msg})
        elif self.path == "/restart":
            ok, msg = CORE.restart()
            if ok:
                AUTOSTART_FILE.touch()
            self._send({"ok": ok, "message": msg}, 200 if ok else 500)
        elif self.path == "/fixroutes":
            self._send({"ok": True, "message": apply_route_fix()})
        elif self.path == "/cleanup_stale":
            # Kill pythonw processes running "app.agent" other than ourselves
            # (older agent instances that failed to exit on reload).
            killed = []
            query = "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='pythonw.exe'"
            for proc in _run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                     "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
                    capture_output=True, text=True).stdout.splitlines():
                try:
                    entries = json.loads(proc)
                    if isinstance(entries, dict):
                        entries = [entries]
                    for entry in entries or []:
                        cmd = entry.get("CommandLine") or ""
                        pid = int(entry.get("ProcessId") or 0)
                        if "app.agent" in cmd and pid and pid != os.getpid():
                            _run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                            killed.append(pid)
                except (ValueError, TypeError):
                    continue
            self._send({"ok": True, "killed": killed})
        elif self.path == "/diagnostics":
            results = {}
            for name, cmd in {
                "wfp_netevents": ["netsh", "wfp", "show", "netevents", f"file={paths.LOG_DIR / 'wfp_netevents.xml'}"],
                "wfp_filters": ["netsh", "wfp", "show", "filters", f"file={paths.LOG_DIR / 'wfp_filters.xml'}"],
                "fltmc": ["fltmc", "filters"],
            }.items():
                out = _run(cmd, capture_output=True, text=True)
                results[name] = (out.stdout + out.stderr)[-4000:]
            self._send(results)
        elif self.path == "/reload":
            # Replace the running agent with one using the latest code.
            # The child inherits this process's elevation, so no new UAC prompt.
            CORE.stop()
            subprocess.Popen([sys.executable, "-m", "app.agent"],
                             cwd=str(paths.ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
            self._send({"ok": True, "message": "reloading agent"})
            _delayed_exit()
        elif self.path == "/shutdown":
            AUTOSTART_FILE.unlink(missing_ok=True)
            CORE.stop()
            self._send({"ok": True, "message": "agent shutting down"})
            _delayed_exit()
        else:
            self._send({"error": "unknown endpoint"}, 404)


def main() -> None:
    setup_logging()
    global TOKEN
    TOKEN = agent_token()
    paths.AGENT_PID_FILE.write_text(str(os.getpid()))
    # A previous agent may have died leaving an orphaned sing-box behind:
    # adopt a clean slate so we never spawn a duplicate core (TUN conflicts).
    _run(["powershell", "-NoProfile", "-Command",
                    "Get-Process sing-box -ErrorAction SilentlyContinue | Stop-Process -Force"],
                   capture_output=True)
    remove_route_fix()
    atexit.register(CORE.stop)
    server = NetPilotHTTPServer((paths.AGENT_ADDR, paths.AGENT_PORT), Handler)
    LOG.info("agent listening on %s:%s", paths.AGENT_ADDR, paths.AGENT_PORT)
    if AUTOSTART_FILE.exists() and not CORE.running():
        threading.Thread(target=CORE.start, daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        CORE.stop()


def _route_fix_present() -> bool:
    gateway = _tun_gateway()
    out = _run(["route", "print", "-4"], capture_output=True, text=True)
    hits = [line for line in out.stdout.splitlines()
            if "128.0.0.0" in line and gateway in line]
    return len(hits) >= 2


def _watchdog() -> None:
    """If the core dies unexpectedly, drop our /1 routes so the machine never
    loses connectivity; restart the core when autostart is enabled. VPN
    reconnects can also wipe our routes, so re-apply the fix when missing."""
    last_restart = 0.0
    while True:
        time.sleep(5)
        try:
            if CORE.running():
                if not _route_fix_present():
                    LOG.warning("watchdog: /1 routes missing, re-applying fix")
                    apply_route_fix()
                continue
            remove_route_fix()
            if AUTOSTART_FILE.exists() and time.time() - last_restart > 30:
                last_restart = time.time()
                LOG.warning("watchdog: core not running, restarting")
                CORE.start()
        except Exception as exc:
            LOG.error("watchdog error: %s", exc)


TOKEN = ""


def _delayed_exit() -> None:
    """The agent must really exit on reload/shutdown: request threads are
    daemonized and we hard-exit after the response is flushed."""
    def _exit():
        time.sleep(0.6)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()


class NetPilotHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    main()
