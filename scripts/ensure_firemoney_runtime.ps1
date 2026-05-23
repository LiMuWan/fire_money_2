param(
    [int]$Port = 8765,
    [string]$BindAddress = "127.0.0.1",
    [int]$BetaIntervalSeconds = 60,
    [double]$MarketDataTimeoutSeconds = 60,
    [object]$AllowMarketDataTimeout = $true,
    [object]$StartPreview = $true,
    [object]$StartBetaWatch = $true,
    [switch]$Loop,
    [int]$LoopIntervalSeconds = 300
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root ".firemoney\logs"
$LogPath = Join-Path $LogDir "firemoney_runtime_watchdog.log"
$PreviewDir = Join-Path $Root "client\desktop\preview"
$RuntimeStatusPath = Join-Path $PreviewDir "runtime_status.json"
$PreviewScript = Join-Path $Root "scripts\start_core_workflow_preview.ps1"
$BetaWatchScript = Join-Path $Root "scripts\start_firemoney_beta_watch.ps1"
$BetaWatchMutexName = "Local\FireMoneyBetaWatch"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-WatchdogLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

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

$AllowMarketDataTimeout = Convert-FireMoneyBool -Value $AllowMarketDataTimeout -Default $true
$StartPreview = Convert-FireMoneyBool -Value $StartPreview -Default $true
$StartBetaWatch = Convert-FireMoneyBool -Value $StartBetaWatch -Default $true

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

function Get-PreviewListeners {
    param(
        [string]$Address,
        [int]$LocalPort
    )
    $listeners = @()
    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction Stop |
            Where-Object {
                $_.LocalAddress -eq $Address -or $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::"
            })
    }
    catch {
        $listeners = @()
    }
    if (($listeners | Measure-Object).Count -gt 0) {
        return $listeners
    }

    $netstatListeners = @()
    $netstatRows = @(netstat -ano -p tcp 2>$null | Select-String ":$LocalPort")
    foreach ($row in $netstatRows) {
        $text = $row.Line.Trim()
        if ($text -notmatch "\sLISTENING\s") {
            continue
        }
        $parts = $text -split "\s+"
        if ($parts.Count -lt 5) {
            continue
        }
        $localEndpoint = $parts[1]
        $processId = $parts[-1]
        $localAddress = $null
        $localEndpointPort = $null
        if ($localEndpoint -match "^\[(?<address>.+)\]:(?<port>\d+)$") {
            $localAddress = $Matches.address
            $localEndpointPort = [int]$Matches.port
        }
        elseif ($localEndpoint -match "^(?<address>.+):(?<port>\d+)$") {
            $localAddress = $Matches.address
            $localEndpointPort = [int]$Matches.port
        }
        if ($localEndpointPort -ne $LocalPort) {
            continue
        }
        if ($localAddress -ne $Address -and $localAddress -ne "0.0.0.0" -and $localAddress -ne "::") {
            continue
        }
        $netstatListeners += [pscustomobject]@{
            LocalAddress = $localAddress
            LocalPort = $localEndpointPort
            OwningProcess = [int]$processId
            State = "Listen"
        }
    }
    return $netstatListeners
}

function Test-PreviewHttp {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return [pscustomobject]@{
            Ok = $response.StatusCode -eq 200 -and $response.Content -match "FireMoney"
            Detail = "http_status=$($response.StatusCode)"
        }
    }
    catch {
        return [pscustomobject]@{
            Ok = $false
            Detail = "http_failed=$($_.Exception.Message)"
        }
    }
}

function Wait-PreviewReady {
    param(
        [string]$Address,
        [int]$LocalPort,
        [string]$Url,
        [int]$TimeoutSeconds = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastHttp = [pscustomobject]@{
        Ok = $false
        Detail = "not_checked"
    }
    do {
        Start-Sleep -Seconds 1
        $listeners = Get-PreviewListeners -Address $Address -LocalPort $LocalPort
        $lastHttp = Test-PreviewHttp -Url $Url
        $listenerCount = ($listeners | Measure-Object).Count
        if ($lastHttp.Ok -and $listenerCount -le 1) {
            return [pscustomobject]@{
                Ok = $true
                Listeners = $listeners
                Http = $lastHttp
            }
        }
    } while ((Get-Date) -lt $deadline)

    return [pscustomobject]@{
        Ok = $false
        Listeners = Get-PreviewListeners -Address $Address -LocalPort $LocalPort
        Http = $lastHttp
    }
}

function Get-BetaWatchProcesses {
    try {
        @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -match "client\.desktop\.firemoney_client\.one_to_two_cli" -and
                $_.CommandLine -match "beta-start" -and
                $_.CommandLine -match "--loop"
            })
    }
    catch {
        @()
    }
}

function Test-NamedMutexHeld {
    param([string]$Name)
    $mutex = $null
    $hasLock = $false
    try {
        $mutex = New-Object System.Threading.Mutex($false, $Name)
        $hasLock = $mutex.WaitOne(0)
        if ($hasLock) {
            return $false
        }
        return $true
    }
    catch [System.Threading.AbandonedMutexException] {
        $hasLock = $true
        return $false
    }
    catch {
        return $false
    }
    finally {
        if ($mutex) {
            if ($hasLock) {
                try {
                    $mutex.ReleaseMutex() | Out-Null
                }
                catch {
                }
            }
            $mutex.Dispose()
        }
    }
}

function Start-DetachedPowerShell {
    param([string]$Arguments)
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -WindowStyle Hidden | Out-Null
}

function Read-ScheduleHealth {
    param([string]$Python)
    Set-Location $Root
    $raw = & $Python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        return [pscustomobject]@{
            Ok = $false
            Raw = ($raw | Out-String).Trim()
            Report = $null
        }
    }
    try {
        return [pscustomobject]@{
            Ok = $true
            Raw = ($raw | Out-String).Trim()
            Report = (($raw | Out-String) | ConvertFrom-Json)
        }
    }
    catch {
        return [pscustomobject]@{
            Ok = $false
            Raw = ($raw | Out-String).Trim()
            Report = $null
        }
    }
}

function Write-RuntimeStatus {
    param(
        [string]$Status,
        [string]$Url,
        [array]$Findings,
        [array]$Actions,
        [object]$ScheduleHealth,
        [string]$BetaWatchState
    )
    try {
        New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null
        $payload = [ordered]@{
            status = $Status
            checked_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            url = $Url
            findings = @($Findings)
            actions = @($Actions)
            beta_watch = $BetaWatchState
            schedule_health_ok = [bool]($ScheduleHealth -and $ScheduleHealth.Ok)
            schedule_health = if ($ScheduleHealth -and $ScheduleHealth.Report) { $ScheduleHealth.Report } else { $null }
            schedule_health_raw = if ($ScheduleHealth -and -not $ScheduleHealth.Report) { $ScheduleHealth.Raw } else { $null }
        }
        $payload | ConvertTo-Json -Depth 12 | Set-Content -Path $RuntimeStatusPath -Encoding UTF8
    }
    catch {
        Write-WatchdogLog "Failed to write runtime status: $($_.Exception.Message)"
    }
}

function Invoke-FireMoneyEnsureOnce {
    $status = "ready"
    $actions = @()
    $findings = @()
    $url = "http://$BindAddress`:$Port/core_workflow.html"
    $betaWatchState = "unknown"

    if (-not (Test-Path $PreviewScript)) {
        $status = "blocked"
        $findings += "preview_start_script_missing"
    }
    if (-not (Test-Path $BetaWatchScript)) {
        $status = "blocked"
        $findings += "beta_watch_start_script_missing"
    }

    $python = $null
    try {
        $python = Resolve-Python
    }
    catch {
        $status = "blocked"
        $findings += "python_missing=$($_.Exception.Message)"
    }

    $health = $null
    if ($python) {
        $health = Read-ScheduleHealth -Python $python
        if (-not $health.Ok) {
            $status = "blocked"
            $findings += "schedule_health_failed"
        }
        elseif ($health.Report.status -eq "blocked") {
            $status = "blocked"
            $findings += "schedule_health_blocked"
        }
        else {
            $findings += "schedule_health=$($health.Report.status)"
            $findings += "is_trading_day=$($health.Report.is_trading_day)"
        }
    }

    $listeners = Get-PreviewListeners -Address $BindAddress -LocalPort $Port
    $listenerCount = ($listeners | Measure-Object).Count
    $httpCheck = Test-PreviewHttp -Url $url
    if ($listenerCount -gt 1) {
        $status = "blocked"
        $findings += "multiple_preview_listeners=$listenerCount"
    }
    elseif ($httpCheck.Ok) {
        if ($listenerCount -eq 1) {
            $listenerProcessId = ($listeners | Select-Object -First 1).OwningProcess
            $findings += "preview_ready_pid=$listenerProcessId"
        }
        else {
            $findings += "preview_ready_http_only"
        }
    }
    elseif ($StartPreview -and $listenerCount -eq 0 -and (Test-Path $PreviewScript)) {
        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PreviewScript`" -Port $Port -BindAddress $BindAddress"
        Start-DetachedPowerShell -Arguments $arguments
        $actions += "started_preview"
        $readyCheck = Wait-PreviewReady -Address $BindAddress -LocalPort $Port -Url $url
        $listeners = $readyCheck.Listeners
        $httpCheck = $readyCheck.Http
        if ($readyCheck.Ok) {
            if ($status -eq "ready") {
                $status = "repaired"
            }
            if (($listeners | Measure-Object).Count -eq 1) {
                $listenerProcessId = ($listeners | Select-Object -First 1).OwningProcess
                $findings += "preview_started_pid=$listenerProcessId"
            }
            else {
                $findings += "preview_started_http_ok"
            }
        }
        else {
            $status = "blocked"
            $findings += "preview_start_failed=$($httpCheck.Detail)"
        }
    }
    elseif ($listenerCount -eq 1) {
        $status = "blocked"
        $findings += "preview_listener_unhealthy=$($httpCheck.Detail)"
    }
    else {
        $status = "blocked"
        $findings += "preview_not_listening"
    }

    $isTradingDay = $false
    if ($health -and $health.Ok -and $health.Report) {
        $isTradingDay = [bool]$health.Report.is_trading_day
    }
    $betaProcesses = Get-BetaWatchProcesses
    $betaCount = ($betaProcesses | Measure-Object).Count
    $betaMutexHeld = Test-NamedMutexHeld -Name $BetaWatchMutexName
    if (-not $StartBetaWatch) {
        $betaWatchState = "disabled"
        $findings += "beta_watch_check_disabled"
    }
    elseif (-not $isTradingDay) {
        $betaWatchState = "not_required_non_trading_day"
        $findings += "beta_watch_not_required_non_trading_day"
    }
    elseif ($betaCount -ge 1) {
        $pids = ($betaProcesses | Select-Object -ExpandProperty ProcessId) -join ","
        $betaWatchState = "running_pid=$pids"
        $findings += "beta_watch_running_pid=$pids"
    }
    elseif ($betaMutexHeld) {
        $betaWatchState = "running_mutex"
        $findings += "beta_watch_running_mutex"
    }
    elseif (Test-Path $BetaWatchScript) {
        $allowText = if ($AllowMarketDataTimeout) { '$true' } else { '$false' }
        $arguments = (
            "-NoProfile -ExecutionPolicy Bypass -File `"$BetaWatchScript`" " +
            "-IntervalSeconds $BetaIntervalSeconds " +
            "-MarketDataTimeoutSeconds $MarketDataTimeoutSeconds " +
            "-AllowMarketDataTimeout:$allowText"
        )
        Start-DetachedPowerShell -Arguments $arguments
        $actions += "started_beta_watch"
        if ($status -eq "ready") {
            $status = "repaired"
        }
        $betaWatchState = "start_requested"
        $findings += "beta_watch_start_requested"
    }
    else {
        $betaWatchState = "missing"
        $status = "blocked"
        $findings += "beta_watch_start_script_missing"
    }

    Write-RuntimeStatus `
        -Status $status `
        -Url $url `
        -Findings $findings `
        -Actions $actions `
        -ScheduleHealth $health `
        -BetaWatchState $betaWatchState

    $summary = "FireMoney runtime ensure: $status"
    Write-Host $summary
    Write-Host "URL: $url"
    foreach ($finding in $findings) {
        Write-Host "- $finding"
    }
    if ($actions.Count -gt 0) {
        Write-Host "Actions: $($actions -join ', ')"
    }
    if ($health -and $health.Raw) {
        Write-Host ""
        Write-Host $health.Raw
    }

    Write-WatchdogLog "$summary; findings=$($findings -join '; '); actions=$($actions -join ', ')"
    if ($status -eq "blocked") {
        exit 1
    }
}

do {
    Invoke-FireMoneyEnsureOnce
    if ($Loop) {
        Start-Sleep -Seconds ([Math]::Max(30, $LoopIntervalSeconds))
    }
} while ($Loop)
