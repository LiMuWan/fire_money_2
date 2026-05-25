param(
    [string]$HostName = "81.70.202.132",
    [string]$User = "ubuntu",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\firemoney_tencent",
    [string]$FeishuEnvPath = "",
    [switch]$StartPreview = $true,
    [switch]$RunBetaCheck = $true,
    [switch]$StartBetaWatch = $true
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH 私钥不存在：$KeyPath"
}
if (-not $FeishuEnvPath) {
    $defaultFeishuEnv = Join-Path (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path ".firemoney") "feishu.env"
    if (Test-Path -LiteralPath $defaultFeishuEnv) {
        $FeishuEnvPath = $defaultFeishuEnv
    }
}
if ($FeishuEnvPath -and -not (Test-Path -LiteralPath $FeishuEnvPath)) {
    throw "飞书环境文件不存在：$FeishuEnvPath"
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DeployScript = Join-Path $Root "scripts\deploy_tencent_ubuntu.ps1"

if (-not (Test-Path -LiteralPath $DeployScript)) {
    throw "找不到部署脚本：$DeployScript"
}

Write-Host "Using host: $HostName"
Write-Host "Using key : $KeyPath"
Write-Host "Delegating to scripts/deploy_tencent_ubuntu.ps1"

$arguments = @(
    "-NoProfile"
    "-ExecutionPolicy"
    "Bypass"
    "-File"
    $DeployScript
    "-HostName"
    $HostName
    "-User"
    $User
    "-KeyPath"
    $KeyPath
)

if ($FeishuEnvPath) {
    Write-Host "Using Feishu env: $FeishuEnvPath"
    $arguments += "-FeishuEnvPath"
    $arguments += $FeishuEnvPath
}

if ($StartPreview) {
    $arguments += "-StartPreview"
}
if ($RunBetaCheck) {
    $arguments += "-RunBetaCheck"
}
if ($StartBetaWatch) {
    $arguments += "-StartBetaWatch"
}

& powershell @arguments
if ($LASTEXITCODE -ne 0) {
    throw "一键部署失败，退出码 $LASTEXITCODE"
}
