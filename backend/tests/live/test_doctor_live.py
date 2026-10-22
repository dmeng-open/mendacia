import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.live
def test_doctor_passes_against_real_model() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.doctor"],
        cwd=BACKEND,
        env=os.environ | {"LLM_MODE": "live"},
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK env" in lines
    assert "OK db" in lines
    assert any(line.startswith("OK model ") for line in lines)
