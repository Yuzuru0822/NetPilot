$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = '1.14.4'
$coreDir = Join-Path $root 'core'
$zip = Join-Path $coreDir 'sing-box.zip'
$url = "https://github.com/SagerNet/sing-box/releases/download/v$version/sing-box-$version-windows-amd64.zip"
New-Item -ItemType Directory -Force $coreDir | Out-Null
Write-Output "Downloading sing-box $version ..."
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $coreDir -Force
Remove-Item $zip
Write-Output "sing-box $version is ready under core/"
