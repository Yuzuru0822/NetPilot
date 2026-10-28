"""GitHub Release auto-update support for NetPilot."""
from __future__ import annotations

import re
from pathlib import Path

import requests

from . import paths

APP_VERSION = "2.2.0"
REPO = "Yuzuru0822/NetPilot"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(tag: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", tag or "")
    return tuple(int(p) for p in parts[:3]) if parts else (0,)


def is_newer(tag: str, current: str = APP_VERSION) -> bool:
    return parse_version(tag) > parse_version(current)


def check_latest(timeout: float = 20.0) -> dict:
    """Return {tag, zip_url, zip_name, notes} for the latest release's zip asset."""
    resp = requests.get(LATEST_API, timeout=timeout,
                        headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    data = resp.json()
    tag = data.get("tag_name", "")
    asset = next((a for a in data.get("assets", [])
                  if a.get("name", "").endswith("-win64.zip")), None)
    if not asset:
        raise RuntimeError("最新 Release 中没有找到 win64 zip 包")
    return {
        "tag": tag,
        "zip_url": asset["browser_download_url"],
        "zip_name": asset["name"],
        "notes": data.get("body", ""),
    }


def download_zip(url: str, dest: Path, progress_cb=None, timeout: float = 30.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 512):
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
    return dest
