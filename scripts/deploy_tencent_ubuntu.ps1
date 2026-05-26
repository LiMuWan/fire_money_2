param(
    [string]$HostName,
    [string]$User = "ubuntu",
    [string]$KeyPath,
    [string]$RemoteDir = "/opt/firemoney",
    [string]$FeishuEnvPath,
    [switch]$StartPreview,
    [switch]$RunBetaCheck,
    [switch]$StartBetaWatch
)

$ErrorActionPreference = "Stop"

if (-not $KeyPath) {
    throw "请提供 SSH 私钥路径，例如：-KeyPath `$env:USERPROFILE\.ssh\firemoney_tencent"
}
if (-not $HostName) {
    throw "请提供服务器公网 IP 或域名，例如：-HostName 1.2.3.4"
}
if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH 私钥不存在：$KeyPath"
}
if ($FeishuEnvPath -and -not (Test-Path -LiteralPath $FeishuEnvPath)) {
    throw "飞书环境文件不存在：$FeishuEnvPath"
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Archive = Join-Path ([System.IO.Path]::GetTempPath()) "firemoney-deploy.tar.gz"
$ReportsArchive = Join-Path ([System.IO.Path]::GetTempPath()) "firemoney-reports.tar.gz"
$RemoteArchive = "/tmp/firemoney-deploy.tar.gz"
$RemoteReportsArchive = "/tmp/firemoney-reports.tar.gz"
$RemoteFeishuEnv = "/tmp/firemoney-feishu.env"
$Target = "$User@$HostName"
$RemoteOwner = "${User}:${User}"
$BetaCheckReady = $false

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

Set-Location $Root

if (Test-Path -LiteralPath $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
if (Test-Path -LiteralPath $ReportsArchive) {
    Remove-Item -LiteralPath $ReportsArchive -Force
}

Write-Host "Packaging FireMoney from $Root"
Invoke-Checked "tar.exe" @(
    "-czf",
    $Archive,
    "--exclude=.git",
    "--exclude=.firemoney",
    "--exclude=.venv",
    "--exclude=__pycache__",
    "--exclude=exports",
    "--exclude=reports",
    "--exclude=build",
    "--exclude=dist",
    "--exclude=.codex_stage",
    "--exclude=client/desktop/preview/*.html",
    "--exclude=client/desktop/preview/*.json",
    "--exclude=client/desktop/preview/*.sqlite3",
    "--exclude=client/desktop/preview/*.png",
    "--exclude=client/desktop/preview/*.tmp",
    "."
)

$ReportsDir = Join-Path (Join-Path $Root ".firemoney") "reports"
$ReportPatterns = @(
    "paper_backtest_*.json",
    "board_shadow_system_*.json"
)
$ReportFiles = @()
if (Test-Path -LiteralPath $ReportsDir) {
    foreach ($pattern in $ReportPatterns) {
        $ReportFiles += Get-ChildItem -LiteralPath $ReportsDir -Filter $pattern -File
    }
}
if ($ReportFiles.Count -gt 0) {
    Write-Host "Packaging public report caches from .firemoney/reports"
    $RootFullPath = (Resolve-Path -LiteralPath $Root).ProviderPath
    $RootFullPath = $RootFullPath.TrimEnd([char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
    $ReportRelativePaths = $ReportFiles |
        Sort-Object FullName -Unique |
        ForEach-Object {
            $FileFullPath = (Resolve-Path -LiteralPath $_.FullName).ProviderPath
            if (-not $FileFullPath.StartsWith($RootFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Report cache path is outside project root: $FileFullPath"
            }
            $relative = $FileFullPath.Substring($RootFullPath.Length)
            $relative = $relative.TrimStart([char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
            $relative -replace "\\", "/"
        }
    $ReportTarArguments = @(
        "-czf",
        $ReportsArchive
    ) + $ReportRelativePaths
    Invoke-Checked "tar.exe" $ReportTarArguments
}

Write-Host "Preparing remote directory $RemoteDir on $Target"
Invoke-Checked "ssh.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Target,
    "sudo mkdir -p '$RemoteDir' && sudo chown '$RemoteOwner' '$RemoteDir'"
)

Write-Host "Stopping FireMoney services before upload"
Invoke-Checked "ssh.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Target,
    "sudo systemctl stop firemoney-beta-watch.service firemoney-preview.service || true && sudo systemctl reset-failed firemoney-beta-watch.service firemoney-preview.service || true"
)

Write-Host "Uploading archive to ${Target}:$RemoteArchive"
Invoke-Checked "scp.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Archive,
    "${Target}:$RemoteArchive"
)

if (Test-Path -LiteralPath $ReportsArchive) {
    Write-Host "Uploading public report caches to ${Target}:$RemoteReportsArchive"
    Invoke-Checked "scp.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $ReportsArchive,
        "${Target}:$RemoteReportsArchive"
    )
}

Write-Host "Installing systemd services on $Target"
Invoke-Checked "ssh.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Target,
    "rm -f '$RemoteDir/client/desktop/preview/'*.html '$RemoteDir/client/desktop/preview/'*.json '$RemoteDir/client/desktop/preview/'*.sqlite3 '$RemoteDir/client/desktop/preview/'*.png '$RemoteDir/client/desktop/preview/'*.tmp 2>/dev/null || true && tar -xzf '$RemoteArchive' -C '$RemoteDir' && sudo bash '$RemoteDir/scripts/linux/install_firemoney_systemd.sh'"
)

if (Test-Path -LiteralPath $ReportsArchive) {
    Write-Host "Installing public report caches on $Target"
    Invoke-Checked "ssh.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $Target,
        "mkdir -p '$RemoteDir/.firemoney/reports' && tar -xzf '$RemoteReportsArchive' -C '$RemoteDir' && rm -f '$RemoteReportsArchive'"
    )
}

if ($FeishuEnvPath) {
    Write-Host "Importing Feishu environment into /etc/firemoney/firemoney.env"
    Invoke-Checked "scp.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $FeishuEnvPath,
        "${Target}:$RemoteFeishuEnv"
    )
    Invoke-Checked "ssh.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $Target,
        "sudo bash '$RemoteDir/scripts/linux/import_firemoney_env.sh' '$RemoteFeishuEnv' && rm -f '$RemoteFeishuEnv' && sudo systemctl daemon-reload"
    )
}

if ($StartPreview) {
    Write-Host "Starting firemoney-preview"
    Invoke-Checked "ssh.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $Target,
        "sudo systemctl restart firemoney-preview && bash '$RemoteDir/scripts/linux/check_firemoney_server.sh'"
    )
}

if ($RunBetaCheck) {
    Write-Host "Running beta-check"
    $betaCheckOutput = & ssh.exe @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $Target,
        "sudo '$RemoteDir/scripts/linux/run_firemoney_cli_with_env.sh' beta-check --market-data-timeout-seconds 20"
    )
    $betaCheckExitCode = $LASTEXITCODE
    $betaCheckOutput | ForEach-Object { Write-Host $_ }
    if ($betaCheckExitCode -ne 0) {
        throw "beta-check failed with exit code $betaCheckExitCode"
    }

    $betaCheckText = $betaCheckOutput -join "`n"
    try {
        $betaCheckJson = $betaCheckText | ConvertFrom-Json
        $BetaCheckReady = ($betaCheckJson.status -eq "ready")
    }
    catch {
        throw "beta-check 输出不是合法 JSON，不能安全启动 beta-watch。"
    }

    if (-not $BetaCheckReady) {
        Write-Warning "beta-check 状态不是 ready，已跳过 beta-watch 启动。请先修复飞书、交易日或体检阻断项。"
        if ($StartBetaWatch) {
            Invoke-Checked "ssh.exe" @(
                "-i",
                $KeyPath,
                "-o",
                "IdentitiesOnly=yes",
                $Target,
                "sudo systemctl stop firemoney-beta-watch.service || true && sudo systemctl reset-failed firemoney-beta-watch.service || true"
            )
        }
    }
}

if ($StartBetaWatch) {
    if ($RunBetaCheck -and -not $BetaCheckReady) {
        Write-Warning "firemoney-beta-watch 未启动：beta-check 未 ready。部署已完成，预览页可用。"
    }
    elseif (-not $RunBetaCheck) {
        Write-Warning "StartBetaWatch requested without RunBetaCheck. 确认 /etc/firemoney/firemoney.env 和 beta-check 已通过后再用于真实值守。"
        Write-Host "Starting firemoney-beta-watch"
        Invoke-Checked "ssh.exe" @(
            "-i",
            $KeyPath,
            "-o",
            "IdentitiesOnly=yes",
            $Target,
            "sudo systemctl restart firemoney-beta-watch && sudo systemctl status firemoney-beta-watch --no-pager"
        )
    }
    else {
        Write-Host "Starting firemoney-beta-watch"
        Invoke-Checked "ssh.exe" @(
            "-i",
            $KeyPath,
            "-o",
            "IdentitiesOnly=yes",
            $Target,
            "sudo systemctl restart firemoney-beta-watch && sudo systemctl status firemoney-beta-watch --no-pager"
        )
    }
}

Write-Host "Deploy complete. Edit secrets only on server: sudo nano /etc/firemoney/firemoney.env"
