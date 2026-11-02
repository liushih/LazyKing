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


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_bootstrap_rejects_incompatible_existing_venv(tools_dir):
    venv_python = tools_dir / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert ".venv" in result.stdout
    assert "bootstrap.ps1" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
@pytest.mark.parametrize("project_id", ["../escape", "nested/id", r"nested\id", ".."])
def test_bootstrap_rejects_unsafe_project_id(tools_dir, project_id):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-CheckOnly", "-PythonCommand", sys.executable,
         "-ProjectId", project_id],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert not (tools_dir.parent / ".data-tools").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_update_ps1_hints_bootstrap_when_failing_without_venv(tmp_path):
    tools = tmp_path / "repo" / "data-tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "update.ps1", tools / "update.ps1")
    (tools / "scripts").mkdir()
    (tools / "scripts" / "update.py").write_text("import sys; sys.exit(1)\n", encoding="utf-8")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools / "update.ps1"), "-CheckOnly", "-Quiet", "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "bootstrap.ps1" in result.stdout
