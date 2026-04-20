import subprocess
from pathlib import Path


def test_check_http_contracts_script_passes():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["python", "scripts/check_http_contracts.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
