param(
    [string]$TaskName = "FireMoneyCoreWorkflowPreview",
    [int]$Port = 8765,
    [string]$BindAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartScript = Join-Path $Root "scripts\start_core_workflow_preview.ps1"

if (-not (Test-Path $StartScript)) {
    throw "Startup script not found: $StartScript"
}

$escapedScript = $StartScript.Replace("'", "''")
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Port $Port -BindAddress $BindAddress"

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
    -Description "Start FireMoney core workflow preview server on 127.0.0.1:$Port. The startup script exits if the port is already in use."

try {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    Write-Host "Registered scheduled task: $TaskName"
    Write-Host "Multiple instances: IgnoreNew; script also exits when the port is already listening."
}
catch {
    $startupDir = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupDir "$TaskName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`" -Port $Port -BindAddress $BindAddress"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = "Start FireMoney core workflow preview server. The script exits if the port is already in use."
    $shortcut.Save()

    Write-Host "Scheduled task registration failed: $($_.Exception.Message)"
    Write-Host "Created current-user Startup shortcut instead: $shortcutPath"
    Write-Host "Instance guard: startup script exits when $BindAddress`:$Port is already listening and also uses a local mutex."
}

Write-Host "Script: $StartScript"
Write-Host "URL: http://$BindAddress`:$Port/core_workflow.html"
