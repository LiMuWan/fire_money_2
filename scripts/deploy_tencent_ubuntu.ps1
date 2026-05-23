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
    Invoke-Checked "ssh.exe" @(
        "-i",
        $KeyPath,
        "-o",
        "IdentitiesOnly=yes",
        $Target,
        "cd '$RemoteDir' && '$RemoteDir/.venv/bin/python' -B -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20"
    )
}

if ($StartBetaWatch) {
    if (-not $RunBetaCheck) {
        Write-Warning "StartBetaWatch requested without RunBetaCheck. 确认 /etc/firemoney/firemoney.env 和 beta-check 已通过后再用于真实值守。"
    }
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

Write-Host "Deploy complete. Edit secrets only on server: sudo nano /etc/firemoney/firemoney.env"
