import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.fixture
def tools_dir(tmp_path):
    tools = tmp_path / "repo" / "data-tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "bootstrap.ps1", tools / "bootstrap.ps1")
    return tools


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_bootstrap_missing_python_prints_download(tools_dir):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-CheckOnly", "-PythonCommand", "definitely-not-python"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "https://www.python.org/downloads/" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_bootstrap_check_only_without_venv_exits_2(tools_dir):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-CheckOnly", "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_update_ps1_passes_check_exit_code(tmp_path):
    tools = tmp_path / "repo" / "data-tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "update.ps1", tools / "update.ps1")
    (tools / "scripts").mkdir()
    (tools / "scripts" / "update.py").write_text("import sys; sys.exit(10)\n", encoding="utf-8")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools / "update.ps1"), "-CheckOnly", "-Quiet", "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 10
