param(
    [string]$TaskName = "FireMoneyRuntimeWatchdog",
    [int]$Port = 8765,
    [string]$BindAddress = "127.0.0.1",
    [int]$BetaIntervalSeconds = 60,
    [double]$MarketDataTimeoutSeconds = 60,
    [object]$AllowMarketDataTimeout = $true,
    [int]$RepeatMinutes = 5
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root ".firemoney\logs"
$LogPath = Join-Path $LogDir "firemoney_startup_registration.log"
$EnsureScript = Join-Path $Root "scripts\ensure_firemoney_runtime.ps1"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-RegistrationLog {
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

function Resolve-InteractiveUserId {
    $whoami = (& whoami 2>$null | Select-Object -First 1)
    if ($whoami -and $whoami -match "\\") {
        return [string]$whoami
    }
    if ($env:USERDOMAIN -and $env:USERNAME) {
        return "$env:USERDOMAIN\$env:USERNAME"
    }
    return $env:USERNAME
}

if (-not (Test-Path $EnsureScript)) {
    throw "Watchdog script not found: $EnsureScript"
}

$AllowMarketDataTimeout = Convert-FireMoneyBool -Value $AllowMarketDataTimeout -Default $true
$allowText = if ($AllowMarketDataTimeout) { '$true' } else { '$false' }
$argument = (
    "-NoProfile -ExecutionPolicy Bypass -File `"$EnsureScript`" " +
    "-Port $Port -BindAddress $BindAddress " +
    "-BetaIntervalSeconds $BetaIntervalSeconds " +
    "-MarketDataTimeoutSeconds $MarketDataTimeoutSeconds " +
    "-AllowMarketDataTimeout:$allowText"
)

try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $Root
    $atLogonTrigger = New-ScheduledTaskTrigger -AtLogOn
    $periodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes)
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -AllowStartIfOnBatteries
    $userId = Resolve-InteractiveUserId
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

    $task = New-ScheduledTask -Action $action -Trigger @($atLogonTrigger, $periodicTrigger) -Settings $settings -Principal $principal `
        -Description "Check FireMoney preview, Beta watch, and morning/eod coverage. Start missing single-instance runtime scripts when needed."

    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    Write-RegistrationLog "Registered scheduled task $TaskName for $userId."
    Write-Host "Registered scheduled task: $TaskName"
    Write-Host "User: $userId"
    Write-Host "Triggers: at logon and every $RepeatMinutes minutes."
    Write-Host "Multiple instances: IgnoreNew; underlying scripts also guard with mutex/port checks."
}
catch {
    Write-RegistrationLog "Scheduled task registration failed for ${TaskName}: $($_.Exception.Message)"
    $startupDir = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupDir "$TaskName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$EnsureScript`" -Loop -LoopIntervalSeconds $($RepeatMinutes * 60) -Port $Port -BindAddress $BindAddress -BetaIntervalSeconds $BetaIntervalSeconds -MarketDataTimeoutSeconds $MarketDataTimeoutSeconds -AllowMarketDataTimeout:$allowText"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = "FireMoney runtime watchdog. Checks preview, Beta watch, and morning/eod coverage."
    $shortcut.Save()
    Write-RegistrationLog "Created Startup shortcut fallback: $shortcutPath"

    Write-Host "Scheduled task registration failed: $($_.Exception.Message)"
    Write-Host "Created current-user Startup shortcut instead: $shortcutPath"
    Write-Host "The shortcut runs watchdog loop every $RepeatMinutes minutes."
}

Write-Host "Script: $EnsureScript"
Write-Host "Manual check: powershell -NoProfile -ExecutionPolicy Bypass -File `"$EnsureScript`""
