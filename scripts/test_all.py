#!/usr/bin/env python3
"""Run tests on Windows, macOS and Linux without shell dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="steward checks ") as tmp:
    env = {k: v for k, v in os.environ.items() if not k.startswith("STEWARD_")}
    env.update(STEWARD_HOME=tmp, STEWARD_WORKDIR=tmp, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    commands = [["agentctl_selftest.py"], ["stewardq_selftest.py"], ["statusline/usage_statusline_selftest.py"],
                ["-m", "unittest", "discover", "-s", "tests", "-v"]]
    for args in commands:
        result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env)
        if result.returncode:
            raise SystemExit(result.returncode)
print("ALL PASS")
