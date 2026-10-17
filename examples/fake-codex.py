#!/usr/bin/env python3
"""Free Codex/local adapter fixture. It never calls a model or reads credentials."""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

if "--version" in sys.argv:
    print("fake-codex 1.0")
    raise SystemExit(0)
if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\n")
prompt = sys.argv[-1]
sid = next((a for a in sys.argv if re.fullmatch(r"[0-9a-f-]{36}", a)), str(uuid.uuid4()))
mode = os.environ.get("FAKE_MODE", "success")


def emit(data):
    print(json.dumps(data), flush=True)


emit({"type": "thread.started", "thread_id": sid})
if mode == "slow":
    time.sleep(3)
match = re.search(r"`([^`]+[\\/]progress\.md)`", prompt)
if match:
    Path(match.group(1)).write_text("## Done\n- fixture run %s\n## Next\n- none\n" % time.time_ns())
if mode == "error":
    emit({"type": "error", "message": "synthetic provider failure"})
elif mode == "empty":
    pass
else:
    emit({"type": "item.completed", "item": {"type": "agent_message", "text": "Fixture completed."}})
    emit({"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 5}})
