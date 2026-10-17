#!/usr/bin/env python3
"""Build deterministic, allow-listed source archives and SHA-256 checksums."""
from __future__ import annotations
import argparse
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["VERSION", "LICENSE", "README.md", "CONTRIBUTING.md", ".env.example", ".gitignore",
         "agentctl.py", "agentctl_selftest.py", "stewardq.py", "stewardq_selftest.py", "steward_config.py",
         "steward_cli.py", "steward_lock.py", "steward_provider.py", "steward_transfer.py", "steward_worker.py",
         "install.py", "setup.sh", "run_tests.sh", "examples", "docs", "statusline", "skills", "tests", "scripts", "launchd"]


def build(output):
    version = (ROOT / "VERSION").read_text().strip()
    name = "steward-" + version
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for rel in FILES:
        p = ROOT / rel
        paths += [f for f in sorted(p.rglob("*")) if f.is_file()] if p.is_dir() else [p]
    paths = [p for p in paths if not p.is_symlink() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    checks = []
    zpath, tpath = output / (name + ".zip"), output / (name + ".tar.gz")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            info = zipfile.ZipInfo(name + "/" + p.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100755 if p.name.endswith(".sh") or p.name == "fake-claude" else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    # Fix gzip metadata too, so the same source produces the same archive bytes.
    import gzip
    with tpath.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for p in paths:
                data = p.read_bytes()
                info = tarfile.TarInfo(name + "/" + p.relative_to(ROOT).as_posix())
                info.size, info.mtime = len(data), 1767225600
                info.mode = 0o755 if p.name.endswith(".sh") or p.name == "fake-claude" else 0o644
                tar.addfile(info, io.BytesIO(data))
    for p in (zpath, tpath):
        checks.append(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name)
        print(p)
    (output / "SHA256SUMS").write_text("\n".join(checks) + "\n")
    return zpath


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default=str(ROOT / "dist"))
    build(Path(p.parse_args().output).resolve())
