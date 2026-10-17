#!/usr/bin/env python3
"""Install a standalone copy. No pip, git, account or network access is required."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent
RUNTIME = ["agentctl.py", "stewardq.py", "steward_config.py", "steward_cli.py", "steward_lock.py",
           "steward_provider.py", "steward_transfer.py", "steward_worker.py", "VERSION", ".env.example", "LICENSE", "README.md", "examples", "statusline", "skills", "docs"]


def install(prefix: Path) -> dict:
    if sys.version_info < (3, 9):
        raise ValueError("Use Python 3.9+ on Windows, macOS or Linux")
    version = (SOURCE / "VERSION").read_text().strip()
    dest = prefix / "share/steward" / version
    binary = prefix / ("bin/steward.cmd" if os.name == "nt" else "bin/steward")
    if binary.exists() and "# Steward installed launcher" not in binary.read_text(errors="replace"):
        raise ValueError("%s already exists and is not a Steward launcher. Select another --prefix." % binary)
    if dest.exists():
        raise ValueError("%s is already installed. Select a different prefix for this copy." % dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".install-", dir=dest.parent))
    try:
        for rel in RUNTIME:
            src = SOURCE / rel
            if src.is_dir():
                shutil.copytree(src, stage / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, stage / rel)
        os.replace(stage, dest)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    binary.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        launcher = '@echo off\nrem # Steward installed launcher\n"%s" -X utf8 "%s" %%*\n' % (
            sys.executable.replace("%", "%%"), str(dest / "steward_cli.py").replace("%", "%%"))
    else:
        launcher = "#!/bin/sh\n# Steward installed launcher\nexec %s -X utf8 %s \"$@\"\n" % (
            shlex.quote(sys.executable), shlex.quote(str(dest / "steward_cli.py")))
    fd, tmp = tempfile.mkstemp(prefix=".steward-", dir=binary.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(launcher)
        os.chmod(tmp, 0o755)
        os.replace(tmp, binary)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    info = {"version": version, "command": str(binary), "runtime": str(dest), "python": sys.executable}
    (dest / "installation.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", default=str(Path.home() / ".local"))
    args = p.parse_args()
    info = install(Path(args.prefix).expanduser().resolve())
    print("Installed Steward %(version)s\nCommand: %(command)s\nRuntime: %(runtime)s" % info)
    cmd = shlex.quote(info["command"])
    print("\nNext:\n  %s init\n  %s demo\n  %s doctor\n\nAdd the command's bin directory to PATH if needed." % (cmd, cmd, cmd))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("install: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
