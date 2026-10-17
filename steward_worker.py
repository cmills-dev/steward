"""Own a pending queue entry through execution and retain refused work for retry."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import agentctl as A
import stewardq as Q
from steward_lock import file_lock


def main():
    source = Path(os.environ["STEWARD_QUEUE_SOURCE"])
    if source.parent.resolve() != Q.PENDING.resolve():
        raise ValueError("invalid queue source")
    with file_lock(Q.QUEUE / "claims" / (source.stem + ".lock"), blocking=False) as claim:
        if claim is None or not source.exists() or Q.entry(source)["run_at"] > Q._now():
            return 0
        args = sys.argv[1:]
        rid = args[args.index("--id") + 1] if args[0] == "run" else args[1]
        before = A.load_state(rid)
        # The manager reserves capacity and keeps its own run claim.
        rc = subprocess.call([sys.executable, str(Q.HERE / "agentctl.py"), *sys.argv[1:]])
        after = A.load_state(rid)
        killed = after.get("status") == "killed" and after != before
        if rc == 79 and not killed:
            Q.defer(source, Q.REFUSED_DEFER_MIN, "manager refused admission; ownership retained")
        elif source.exists():
            Q._finish(source, "-killed" if killed else "-failed" if rc not in (0, 76, 77, 80) else "")
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
