# 业务仓库引导：检测 Python 3.11+、创建 .venv 并安装依赖
# 用法：powershell -ExecutionPolicy Bypass -File .\data-tools\bootstrap.ps1 [-ProjectId <id>] [-CheckOnly]
param(
    [string]$ProjectId,
    [switch]$CheckOnly,
    [string]$PythonCommand
)

$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$root = Split-Path $tools -Parent
$venvPython = Join-Path $tools '.venv\Scripts\python.exe'
$downloadUrl = 'https://www.python.org/downloads/'

if ($ProjectId -and $ProjectId -match '[\\/]|\.\.') {
    Write-Host "无效的 ProjectId：$ProjectId（不能包含路径分隔符或 '..'）"
    exit 1
}

function Test-PythonAt {
    param([string]$Exe, [string[]]$Prefix = @())

    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue) -and -not (Test-Path $Exe)) {
        return $false
    }

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = (& $Exe @Prefix --version 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }

    if ($exitCode -ne 0) { return $false }
    if ($output -notmatch 'Python\s+(\d+)\.(\d+)') { return $false }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
}

function Find-Python {
    if (Test-Path $venvPython) {
        if (Test-PythonAt -Exe $venvPython) { return @($venvPython) }
    }
    if ($PythonCommand) {
        if (Test-PythonAt -Exe $PythonCommand) { return @($PythonCommand) }
        return
    }
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.11', '-3')) {
            if (Test-PythonAt -Exe 'py' -Prefix @($version)) { return @('py', $version) }
        }
    }
    foreach ($exe in @('python', 'python3')) {
        if (Test-PythonAt -Exe $exe) { return @($exe) }
    }
    return
}

$python = @(Find-Python)
if ($python.Count -eq 0) {
    Write-Host '未找到 Python 3.11 或更高版本。'
    Write-Host "请从 $downloadUrl 安装后重试。"
    exit 1
}

if ($CheckOnly) {
    if (Test-Path $venvPython) { exit 0 }
    exit 2
}

if ((Test-Path $venvPython) -and -not (Test-PythonAt -Exe $venvPython)) {
    Write-Host '检测到 data-tools/.venv，但其 Python 不可用或低于 3.11。'
    Write-Host '请删除或重命名 data-tools/.venv 后重新运行 bootstrap.ps1。'
    exit 1
}

$exe = $python[0]
$prefix = @()
if ($python.Count -gt 1) { $prefix = $python[1..($python.Count - 1)] }

if (-not (Test-Path $venvPython)) {
    Write-Host '[bootstrap] 创建虚拟环境 .venv' -ForegroundColor Cyan
    & $exe @prefix -m venv (Join-Path $tools '.venv')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host '[bootstrap] 升级 pip' -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host '[bootstrap] 安装依赖' -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $tools 'requirements.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($ProjectId) {
    $projectDir = Join-Path $root ".data-tools\projects\$ProjectId"
    New-Item -ItemType Directory -Force -Path $projectDir | Out-Null
    Write-Host "[bootstrap] 已创建项目目录 $projectDir" -ForegroundColor Cyan
}

Write-Host '[bootstrap] 初始化完成' -ForegroundColor Green
