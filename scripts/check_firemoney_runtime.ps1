param(
    [int]$Port = 8765,
    [string]$BindAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Url = "http://$BindAddress`:$Port/core_workflow.html"
$PreviewDir = Join-Path $Root "client\desktop\preview"
$RuntimeStatusPath = Join-Path $PreviewDir "runtime_status.json"
$BetaWatchMutexName = "Local\FireMoneyBetaWatch"

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

Set-Location $Root

$status = "ready"
$findings = @()
$listeners = Get-PreviewListeners -Address $BindAddress -LocalPort $Port
$listenerCount = ($listeners | Measure-Object).Count

if ($listenerCount -gt 1) {
    $status = "blocked"
    $findings += "multiple_preview_listeners=$listenerCount"
}
elseif ($listenerCount -eq 1) {
    $processId = ($listeners | Select-Object -First 1).OwningProcess
    $findings += "preview_listener_pid=$processId"
}
else {
    $findings += "preview_listener_not_seen"
}

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
    if ($response.StatusCode -ne 200) {
        $status = "blocked"
        $findings += "preview_http_status=$($response.StatusCode)"
    }
    elseif ($response.Content -notmatch "FireMoney") {
        $status = "warning"
        $findings += "preview_content_missing_firemoney"
    }
    else {
        $findings += "preview_http_200"
        if ($status -ne "blocked" -and $listenerCount -eq 0) {
            $findings += "preview_http_ok_listener_probe_unavailable"
        }
    }
}
catch {
    $status = "blocked"
    $findings += "preview_http_failed=$($_.Exception.Message)"
}

$healthReport = $null
$healthJsonRaw = & python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health 2>&1
$healthJsonExit = $LASTEXITCODE
if ($healthJsonExit -eq 0) {
    try {
        $healthReport = ($healthJsonRaw | Out-String) | ConvertFrom-Json
    }
    catch {
        $findings += "schedule_health_json_parse_failed=$($_.Exception.Message)"
    }
}
else {
    $findings += "schedule_health_json_failed=$healthJsonExit"
}

$health = & python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief 2>&1
$healthExit = $LASTEXITCODE
if ($healthExit -ne 0) {
    $status = "blocked"
    $findings += "schedule_health_failed=$healthExit"
}

$paperDbSummary = $null
try {
    $paperDbRaw = & python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db 2>&1
    if ($LASTEXITCODE -eq 0) {
        $paperDb = ($paperDbRaw | Out-String) | ConvertFrom-Json
        $paperTone = "neutral"
        $paperHeadline = "真实模拟盘样本不足，不能证明赚钱能力。"
        $paperAction = "继续小样本模拟，买卖必须入库复盘。"
        if ([int]$paperDb.closed_trade_count -gt 0) {
            if ([double]$paperDb.total_realized_pnl -lt 0) {
                $paperTone = "danger"
                $paperHeadline = "真实模拟盘仍在亏损，先暂停放宽仓位。"
                $paperAction = "先复盘亏损样本、买点质量和卖点纪律。"
            }
            elseif ([double]$paperDb.average_profit_drawdown_ratio -lt 1.0) {
                $paperTone = "warning"
                $paperHeadline = "真实模拟盘收益质量未达标，盈利还没覆盖回撤。"
                $paperAction = "只允许小仓验证，不允许因为样例好看而加仓。"
            }
            elseif ([double]$paperDb.win_rate -lt 0.55 -or [double]$paperDb.risk_quality_pass_rate -lt 0.6) {
                $paperTone = "warning"
                $paperHeadline = "真实模拟盘有收益，但胜率或质量还不稳。"
                $paperAction = "继续按指挥单执行，暂不放宽仓位。"
            }
            else {
                $paperTone = "success"
                $paperHeadline = "真实模拟盘收益质量暂时达标。"
                $paperAction = "可按指挥单执行，但仍坚持每天最多一笔。"
            }
        }
        $latestTrade = $null
        if ($paperDb.recent_trades -and $paperDb.recent_trades.Count -gt 0) {
            $latestTrade = $paperDb.recent_trades[0]
        }
        $paperDbSummary = [ordered]@{
            status = [string]$paperDb.status
            tone = $paperTone
            headline = $paperHeadline
            action = $paperAction
            last_trade_date = [string]$paperDb.last_trade_date
            equity = [double]$paperDb.equity
            total_realized_return_pct = [double]$paperDb.total_realized_return_pct
            win_rate = [double]$paperDb.win_rate
            average_profit_drawdown_ratio = [double]$paperDb.average_profit_drawdown_ratio
            risk_quality_pass_rate = [double]$paperDb.risk_quality_pass_rate
            closed_trade_count = [int]$paperDb.closed_trade_count
            open_position_count = [int]$paperDb.open_position_count
            latest_trade = if ($latestTrade) {
                [ordered]@{
                    name = [string]$latestTrade.name
                    symbol = [string]$latestTrade.symbol
                    realized_pnl_pct = [double]$latestTrade.realized_pnl_pct
                    exit_reason = [string]$latestTrade.exit_reason
                }
            } else {
                $null
            }
        }
    }
    else {
        $findings += "paper_db_failed=$LASTEXITCODE"
    }
}
catch {
    $findings += "paper_db_summary_failed=$($_.Exception.Message)"
}

function Write-RuntimeStatusSnapshot {
    param(
        [string]$Status,
        [string]$Url,
        [array]$Findings,
        [object]$HealthOutput,
        [object]$PaperDbSummary,
        [string]$BetaWatchState
    )
    try {
        New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null
        $payload = [ordered]@{
            status = $Status
            checked_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            url = $Url
            findings = @($Findings)
            actions = @()
            beta_watch = $BetaWatchState
            schedule_health_ok = ($HealthOutput -join "`n") -match "FireMoney 值守稳定性诊断：ready"
            schedule_health = $null
            schedule_health_raw = ($HealthOutput | Out-String).Trim()
            paper_db = $PaperDbSummary
        }
        $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $RuntimeStatusPath -Encoding UTF8
    }
    catch {
        Write-Host "- runtime_status_write_failed=$($_.Exception.Message)"
    }
}

if (($health | Out-String) -match "FireMoney 值守稳定性诊断：blocked") {
    $status = "blocked"
    $findings += "schedule_health_blocked"
}
elseif (($health | Out-String) -match "FireMoney 值守稳定性诊断：warning" -and $status -eq "ready") {
    $status = "warning"
    $findings += "schedule_health_warning"
}

$betaWatchState = "unknown"
$isTradingDay = $false
if ($healthReport) {
    $isTradingDay = [bool]$healthReport.is_trading_day
}
$betaProcesses = Get-BetaWatchProcesses
$betaCount = ($betaProcesses | Measure-Object).Count
$betaMutexHeld = Test-NamedMutexHeld -Name $BetaWatchMutexName
if (-not $isTradingDay) {
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
else {
    $betaWatchState = "missing"
    $status = "blocked"
    $findings += "beta_watch_missing"
}

Write-RuntimeStatusSnapshot -Status $status -Url $Url -Findings $findings -HealthOutput $health -PaperDbSummary $paperDbSummary -BetaWatchState $betaWatchState

Write-Host "FireMoney runtime health: $status"
Write-Host "URL: $Url"
foreach ($finding in $findings) {
    Write-Host "- $finding"
}
Write-Host ""
Write-Host $health

if ($status -eq "blocked") {
    exit 1
}
exit 0
