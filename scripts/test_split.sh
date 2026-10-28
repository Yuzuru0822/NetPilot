#!/bin/bash
# Minimal end-to-end split test: curl.exe must egress via FastOrange (Tokyo),
# everything else via the physical adapter (China direct).
set -u
cd "$(dirname "$0")/.."
TOKEN=$(cat data/agent.token)
H="X-NetPilot-Token: $TOKEN"
echo "=== agent status ==="
curl -s -H "$H" http://127.0.0.1:19090/status
echo
echo "=== start sing-box ==="
curl -s -X POST -H "$H" http://127.0.0.1:19090/start
echo
sleep 2
echo "=== routes after sing-box start ==="
route print -4 | sed -n '/Active Routes/,/Persistent/p' | head -35
echo "=== curl.exe (rule: fastorange) ==="
curl -s --max-time 20 https://ipinfo.io/json
echo
echo "=== powershell.exe (no rule: direct) ==="
powershell -NoProfile -Command "(Invoke-RestMethod -Uri 'https://ipinfo.io/json' -TimeoutSec 20) | Select-Object ip,city,country | ConvertTo-Json -Compress"
echo "=== nslookup google.com ==="
nslookup google.com 2>&1 | tail -6
