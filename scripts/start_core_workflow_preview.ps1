param(
    [int]$Port = 8765,
    [string]$BindAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PreviewDir = Join-Path $Root "client\desktop\preview"
$LogDir = Join-Path $Root ".firemoney\logs"
$LogPath = Join-Path $LogDir "core_workflow_preview.log"
$MutexName = "Local\FireMoneyCoreWorkflowPreview8765"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-PreviewLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Test-PreviewPort {
    param(
        [string]$Address,
        [int]$LocalPort
    )
    $listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) {
        return $false
    }
    return [bool]($listeners | Where-Object {
        $_.LocalAddress -eq $Address -or $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::"
    } | Select-Object -First 1)
}

function Wait-PreviewPort {
    param(
        [string]$Address,
        [int]$LocalPort,
        [int]$TimeoutSeconds = 15
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-PreviewPort -Address $Address -LocalPort $LocalPort) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Resolve-Python {
    $candidates = @()
    if ($env:FIREMONEY_PYTHON) {
        $candidates += $env:FIREMONEY_PYTHON
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += $command.Source
    }
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }
    throw "Could not find python.exe. Set FIREMONEY_PYTHON to the Python executable path."
}

function New-Utf8PreviewServerScript {
    param(
        [string]$TargetPath
    )
    @'
from __future__ import annotations

import http.server
from http.server import ThreadingHTTPServer
import sys


class Utf8HtmlRequestHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        content_type = super().guess_type(path)
        if content_type == "text/html":
            return "text/html; charset=utf-8"
        return content_type


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    bind = "127.0.0.1"
    if "--bind" in sys.argv:
        index = sys.argv.index("--bind")
        if index + 1 < len(sys.argv):
            bind = sys.argv[index + 1]
    with ReusableThreadingHTTPServer((bind, port), Utf8HtmlRequestHandler) as httpd:
        httpd.serve_forever()
'@ | Set-Content -Path $TargetPath -Encoding UTF8
}

if (-not (Test-Path $PreviewDir)) {
    throw "Preview directory not found: $PreviewDir"
}

$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$hasLock = $false
$python = $null
$serverScript = $null
try {
    $hasLock = $mutex.WaitOne(0)
    if (-not $hasLock) {
        if (Test-PreviewPort -Address $BindAddress -LocalPort $Port) {
            Write-PreviewLog "Startup lock is held, but server is already listening on $BindAddress`:$Port. Exit."
            exit 0
        }
        Write-PreviewLog "Startup lock is held while port is not listening; continuing so watchdog can repair a stale startup."
    }

    if (Test-PreviewPort -Address $BindAddress -LocalPort $Port) {
        Write-PreviewLog "Server already listening on $BindAddress`:$Port. Exit."
        exit 0
    }

    $python = Resolve-Python
    Write-PreviewLog "Refreshing core workflow preview HTML before serving."
    Set-Location $Root
    & $python -B -m client.desktop.firemoney_client.preview
    $previewExitCode = $LASTEXITCODE
    if ($previewExitCode -ne 0) {
        Write-PreviewLog "Preview generation failed with code $previewExitCode."
        exit $previewExitCode
    }
    $serverScript = Join-Path $LogDir "utf8_preview_server.py"
    New-Utf8PreviewServerScript -TargetPath $serverScript
}
finally {
    if ($hasLock) {
        $mutex.ReleaseMutex() | Out-Null
    }
    $mutex.Dispose()
}

Write-PreviewLog "Starting UTF-8 server with $python on $BindAddress`:$Port, directory $PreviewDir."
Push-Location $PreviewDir
try {
    & $python -B $serverScript $Port --bind $BindAddress
    $exitCode = $LASTEXITCODE
    Write-PreviewLog "Server process exited with code $exitCode."
    exit $exitCode
}
finally {
    Pop-Location
}
