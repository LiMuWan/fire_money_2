param(
    [string]$HostName,
    [string]$User = "ubuntu",
    [string]$KeyPath,
    [string]$RemoteDir = "/opt/firemoney",
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

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Archive = Join-Path ([System.IO.Path]::GetTempPath()) "firemoney-deploy.tar.gz"
$RemoteArchive = "/tmp/firemoney-deploy.tar.gz"
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
    "."
)

Write-Host "Preparing remote directory $RemoteDir on $Target"
Invoke-Checked "ssh.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Target,
    "sudo mkdir -p '$RemoteDir' && sudo chown '$RemoteOwner' '$RemoteDir'"
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

Write-Host "Installing systemd services on $Target"
Invoke-Checked "ssh.exe" @(
    "-i",
    $KeyPath,
    "-o",
    "IdentitiesOnly=yes",
    $Target,
    "tar -xzf '$RemoteArchive' -C '$RemoteDir' && sudo bash '$RemoteDir/scripts/linux/install_firemoney_systemd.sh'"
)

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
        "cd '$RemoteDir' && '$RemoteDir/.venv/bin/python' -B -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20"
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
                "sudo systemctl stop firemoney-beta-watch || true"
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
