param(
    [int]$IntervalSeconds = 60,
    [double]$MarketDataTimeoutSeconds = 60,
    [string]$TradeDate = "",
    [object]$AllowMarketDataTimeout = $true
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root ".firemoney\logs"
$LogPath = Join-Path $LogDir "firemoney_beta_watch.log"
$MutexName = "Local\FireMoneyBetaWatch"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Convert-FireMoneyBool {
    param(
        [object]$Value,
        [bool]$Default = $true
    )
    if ($null -eq $Value) {
        return $Default
    }
    if ($Value -is [bool]) {
        return [bool]$Value
    }
    $text = ([string]$Value).Trim().ToLowerInvariant()
    if ($text -in @("0", "false", "`$false", "no", "off")) {
        return $false
    }
    if ($text -in @("1", "true", "`$true", "yes", "on")) {
        return $true
    }
    return [bool]$Value
}

function Write-BetaLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
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

$AllowMarketDataTimeout = Convert-FireMoneyBool -Value $AllowMarketDataTimeout -Default $true

$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$hasLock = $false
try {
    $hasLock = $mutex.WaitOne(0)
    if (-not $hasLock) {
        Write-BetaLog "Another beta-start loop is already running. Exit."
        exit 0
    }

    $python = Resolve-Python
    $arguments = @(
        "-B",
        "-m",
        "client.desktop.firemoney_client.one_to_two_cli",
        "beta-start",
        "--loop",
        "--interval-seconds",
        "$IntervalSeconds",
        "--market-data-timeout-seconds",
        "$MarketDataTimeoutSeconds"
    )
    if ($AllowMarketDataTimeout) {
        $arguments += "--allow-market-data-timeout"
    }
    if ($TradeDate) {
        $arguments += @("--trade-date", $TradeDate)
    }

    Write-BetaLog "Starting beta watch with $python $($arguments -join ' ')"
    Set-Location $Root
    & $python @arguments
    $exitCode = $LASTEXITCODE
    Write-BetaLog "beta-start exited with code $exitCode."
    exit $exitCode
}
finally {
    if ($hasLock) {
        $mutex.ReleaseMutex() | Out-Null
    }
    $mutex.Dispose()
}
