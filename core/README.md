# sing-box core

The sing-box Windows binaries are **not** stored in git (large, third-party).
Download them with:

```powershell
D:\NetPilot\scripts\download_core.ps1
```

This fetches sing-box **v1.14.4** (`sing-box-1.14.4-windows-amd64.zip` from the
official SagerNet/sing-box releases) and extracts it here, producing:

```
core/sing-box-1.14.4-windows-amd64/sing-box.exe
core/sing-box-1.14.4-windows-amd64/libcronet.dll
```

To upgrade, change `$version` in `scripts/download_core.ps1` and update the
`CORE_EXE` path in `app/paths.py` if the folder name changes.
