#!/usr/bin/env python3
"""Steward's installed command. Python standard library only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent


def initialise() -> int:
    from steward_config import ROOT
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    for rel in ["runs", "health", "queue/pending", "queue/done"]:
        (ROOT / rel).mkdir(parents=True, exist_ok=True, mode=0o700)
    config = ROOT / ".env"
    if not config.exists():
        with config.open("x", encoding="utf-8") as f:
            f.write((HERE / ".env.example").read_text())
        config.chmod(0o600)
    print("Steward state: %s\nConfiguration: %s\nExisting settings are preserved." % (ROOT, config))
    return 0


def doctor(as_json=False) -> int:
    from steward_config import CLAUDE, ROOT, DEFAULT_WORKDIR
    checks = []

    def add(name, ok, detail, required=True):
        checks.append(dict(check=name, ok=ok, detail=detail, required=required))

    add("python", sys.version_info >= (3, 9), sys.version.split()[0])
    add("platform", os.name in ("posix", "nt"), sys.platform)
    add("state", ROOT.is_dir() and os.access(ROOT, os.W_OK), str(ROOT) + "; run steward init if missing")
    add("workdir", DEFAULT_WORKDIR.is_dir(), str(DEFAULT_WORKDIR))
    found = CLAUDE.is_file() and os.access(CLAUDE, os.X_OK)
    add("claude", found, str(CLAUDE) + "; authentication is not checked", required=False)
    import steward_provider
    codex = steward_provider.codex_binary()
    add("codex", bool(shutil.which(codex) or Path(codex).is_file()), codex + "; authentication is not checked", False)
    engine = os.environ.get("STEWARD_LOCAL_PROVIDER", "ollama")
    add("local", bool(shutil.which("ollama")) if engine == "ollama" else True,
        engine + "; needs a running server, Codex CLI and a tool-capable model; no connection was made", False)
    import agentctl
    usage = agentctl.usage_now()
    add("claude_usage", bool(usage.get("fresh")),
        "fresh sensor reading" if usage.get("fresh") else "missing or stale; proactive wind-down needs the status-line sensor", False)
    result = {"version": (HERE / "VERSION").read_text().strip(), "checks": checks,
              "ok": all(c["ok"] for c in checks if c["required"])}
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        for c in checks:
            print("%s %s: %s" % ("OK" if c["ok"] else "ERROR" if c["required"] else "NOTE", c["check"], c["detail"]))
        print("Demo: steward demo. Live runs require an installed, authenticated provider CLI.")
    return 0 if result["ok"] else 1


def demo() -> int:
    """Exercise the installed manager with a fake CLI and disposable state."""
    with tempfile.TemporaryDirectory(prefix="steward demo ") as tmp:
        root = Path(tmp)
        work = root / "sample project"
        work.mkdir()
        env = dict(os.environ, STEWARD_HOME=str(root / "state"), STEWARD_WORKDIR=str(work),
                   STEWARD_CLAUDE=str(HERE / "examples/fake-claude"), STEWARD_KEEP_API_KEY="")
        env.pop("DEMO_SLEEP", None)
        argv = [sys.executable, str(HERE / "agentctl.py"), "run", "--id", "demo",
                "--provider", "claude",
                "--brief", str(HERE / "examples/hello-brief.md"), "--repo", str(work), "--max-minutes", "1"]
        print("Running a disposable demonstration. No account or model call is used.", flush=True)
        p = subprocess.run(argv, env=env, timeout=50)
        if p.returncode:
            return p.returncode
        state = json.loads((root / "state/runs/demo/state.json").read_text())
        if state.get("status") != "done" or not (work / "steward-hello.txt").is_file():
            print("Demo failed to produce its expected result.", file=sys.stderr)
            return 1
        print("DEMO PASS: managed run, checkpoint and result verified. Demo state will be removed.")
        return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Run, checkpoint and resume local coding agents.", add_help=False)
    parser.add_argument("--home", help="State directory, default ~/.steward")
    parser.add_argument("--version", action="store_true")
    opts, rest = parser.parse_known_args(argv)
    if opts.home:
        os.environ["STEWARD_HOME"] = str(Path(opts.home).expanduser().resolve())
    if opts.version:
        print("Steward " + (HERE / "VERSION").read_text().strip())
        return 0
    if not rest or rest[0] in ("-h", "--help"):
        print("Steward\n\nUsage: steward [--home DIR] COMMAND [ARGS]\n\n"
              "  init              Create private state and example configuration\n"
              "  doctor [--json]   Check the installation without a model call\n"
              "  demo              Run a free, disposable example\n  export, import    Move a task checkpoint between computers\n"
              "  queue ...         Add, list or dispatch scheduled work\n"
              "  watch [--interval 60]  Dispatch due work until stopped\n"
              "  run, resume, pause, kill, status, logs, report, usage, gc\n\n"
              "Use steward run --help or steward queue --help for options.")
        return 0
    command, args = rest[0], rest[1:]
    if command == "watch":
        wp = argparse.ArgumentParser(prog="steward watch")
        wp.add_argument("--interval", type=int, default=60)
        wa = wp.parse_args(args)
        if wa.interval < 1:
            wp.error("interval must be positive")
        import stewardq
        print("Watching this machine's queue. Keep it awake. Ctrl+C stops the watcher.", flush=True)
        try:
            while True:
                stewardq.tick()
                time.sleep(wa.interval)
        except KeyboardInterrupt:
            return 0
    if command == "init":
        if args:
            parser.error("init takes no arguments")
        return initialise()
    if command == "doctor":
        if args not in ([], ["--json"]):
            parser.error("doctor accepts only --json")
        return doctor(args == ["--json"])
    if command == "demo":
        if args:
            parser.error("demo takes no arguments")
        return demo()
    # Retain the tested standalone command entry points.
    if command == "queue":
        import stewardq
        sys.argv = ["steward queue", *args]
        return stewardq.main()
    if command in ("export", "import"):
        import steward_transfer
        return steward_transfer.main(command, args)
    import agentctl
    sys.argv = ["steward", command, *args]
    return agentctl.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print("steward: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
