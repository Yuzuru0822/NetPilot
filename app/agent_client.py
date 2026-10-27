"""HTTP clients for the NetPilot agent and the sing-box Clash API."""
from __future__ import annotations

import requests

from . import paths


class AgentOffline(Exception):
    pass


class AgentClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @staticmethod
    def _headers() -> dict:
        try:
            token = (paths.DATA_DIR / "agent.token").read_text().strip()
        except OSError:
            token = ""
        return {"X-NetPilot-Token": token}

    def _call(self, method: str, endpoint: str) -> dict:
        try:
            resp = requests.request(method, paths.AGENT_BASE + endpoint,
                                    headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise AgentOffline(str(exc)) from exc
        try:
            return resp.json()
        except ValueError:
            return {"ok": resp.ok, "message": resp.text}

    def status(self) -> dict:
        return self._call("GET", "/status")

    def start(self) -> dict:
        return self._call("POST", "/start")

    def stop(self) -> dict:
        return self._call("POST", "/stop")

    def restart(self) -> dict:
        return self._call("POST", "/restart")

    def reload(self) -> dict:
        return self._call("POST", "/reload")

    def shutdown(self) -> dict:
        return self._call("POST", "/shutdown")

    def fixroutes(self) -> dict:
        return self._call("POST", "/fixroutes")

    def diagnostics(self) -> dict:
        return self._call("POST", "/diagnostics")

    def singbox_log(self) -> str:
        return self._call("GET", "/singbox-log").get("log", "")

    def online(self) -> bool:
        try:
            self.status()
            return True
        except AgentOffline:
            return False


class ClashClient:
    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    def _get(self, endpoint: str) -> dict:
        resp = requests.get(paths.CLASH_BASE + endpoint,
                            headers={"Authorization": f"Bearer {paths.CLASH_SECRET}"},
                            timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def connections(self) -> list[dict]:
        return self._get("/connections").get("connections") or []

    def close_connection(self, conn_id: str) -> None:
        requests.delete(paths.CLASH_BASE + "/connections/" + conn_id,
                        headers={"Authorization": f"Bearer {paths.CLASH_SECRET}"},
                        timeout=self.timeout)
