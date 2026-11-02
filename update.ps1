# 检查并更新 data-tools
# 用法：powershell -ExecutionPolicy Bypass -File .\data-tools\update.ps1 [-CheckOnly] [-Quiet]
param(
    [switch]$CheckOnly,
    [switch]$Quiet,
    [string]$PythonCommand
)

$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$root = Split-Path $tools -Parent
$venvPython = Join-Path $tools '.venv\Scripts\python.exe'
$downloadUrl = 'https://www.python.org/downloads/'

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

$venvReady = (Test-Path $venvPython) -and (Test-PythonAt -Exe $venvPython)

$exe = $python[0]
$prefix = @()
if ($python.Count -gt 1) { $prefix = $python[1..($python.Count - 1)] }

$arguments = @((Join-Path $tools 'scripts\update.py'), '--project-dir', $root)
if ($CheckOnly) { $arguments += '--check' }
if ($Quiet) { $arguments += '--quiet' }

& $exe @prefix @arguments
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0 -and $exitCode -ne 10 -and -not $venvReady) {
    Write-Host '提示：data-tools/.venv 不可用，请先运行 bootstrap.ps1 创建虚拟环境并安装依赖。'
}
exit $exitCode
