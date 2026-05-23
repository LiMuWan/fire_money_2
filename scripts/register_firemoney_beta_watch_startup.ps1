param(
    [string]$TaskName = "FireMoneyBetaWatch",
    [int]$IntervalSeconds = 60,
    [double]$MarketDataTimeoutSeconds = 60,
    [object]$AllowMarketDataTimeout = $true
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartScript = Join-Path $Root "scripts\start_firemoney_beta_watch.ps1"

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

if (-not (Test-Path $StartScript)) {
    throw "Startup script not found: $StartScript"
}

$AllowMarketDataTimeout = Convert-FireMoneyBool -Value $AllowMarketDataTimeout -Default $true
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -IntervalSeconds $IntervalSeconds -MarketDataTimeoutSeconds $MarketDataTimeoutSeconds -AllowMarketDataTimeout:`$$AllowMarketDataTimeout"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Days 999) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Start FireMoney beta-start watch loop. The startup script exits if another watch loop is already running."

try {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    Write-Host "Registered scheduled task: $TaskName"
    Write-Host "Multiple instances: IgnoreNew; script also exits when another loop already holds the local mutex."
}
catch {
    $startupDir = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupDir "$TaskName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`" -IntervalSeconds $IntervalSeconds -MarketDataTimeoutSeconds $MarketDataTimeoutSeconds -AllowMarketDataTimeout:`$$AllowMarketDataTimeout"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = "Start FireMoney beta-start watch loop. The script exits if another loop is already running."
    $shortcut.Save()

    Write-Host "Scheduled task registration failed: $($_.Exception.Message)"
    Write-Host "Created current-user Startup shortcut instead: $shortcutPath"
}

Write-Host "Script: $StartScript"
Write-Host "Loop: beta-start --loop --interval-seconds $IntervalSeconds --market-data-timeout-seconds $MarketDataTimeoutSeconds --allow-market-data-timeout=$AllowMarketDataTimeout"
