"""Explicit provider commands and translation of native Codex JSON events."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys

PROVIDERS = ("claude", "codex", "local")


def validate(name):
    if name not in PROVIDERS:
        raise ValueError("provider must be claude, codex or local")
    return name


def metadata(project, tags):
    if not isinstance(project, str) or len(project) > 160 or any(c in project for c in "\r\n"):
        raise ValueError("project must be one line of at most 160 characters")
    if not isinstance(tags, list) or len(tags) > 32 or any(
            not isinstance(t, str) or not t or len(t) > 80 or any(c in t for c in ",\r\n") for t in tags):
        raise ValueError("use up to 32 non-empty tags without commas or newlines")


def model_for(provider, model=""):
    validate(provider)
    model = model or os.environ.get("STEWARD_%s_MODEL" % provider.upper(), "gpt-6.1-sol" if provider == "codex" else "")
    if provider == "local" and not model:
        raise ValueError("local runs need --model or STEWARD_LOCAL_MODEL")
    if provider == "codex" and model.startswith("claude-") or provider == "claude" and model.startswith("gpt-"):
        raise ValueError("model and provider disagree")
    return model


def codex_binary():
    return str(Path(os.environ["STEWARD_CODEX"]).expanduser()) if os.environ.get("STEWARD_CODEX") else (shutil.which("codex") or "codex")


def executable(binary):
    try:
        with Path(binary).open("rb") as f:
            if Path(binary).suffix == ".py" or f.readline(160).startswith(b"#!/usr/bin/env python"):
                return [sys.executable, str(binary)]
    except OSError:
        pass
    return [str(binary)]


def command(provider, prompt, model, progress, resume="", local_provider=""):
    validate(provider)
    if provider == "claude":
        raise ValueError("the Claude adapter builds its own command")
    args = executable(codex_binary()) + ["--ask-for-approval", "never", "--sandbox", "workspace-write",
            "--add-dir", str(progress.parent)]
    if provider == "local":
        backend = local_provider or os.environ.get("STEWARD_LOCAL_PROVIDER", "ollama")
        if backend not in ("ollama", "lmstudio"):
            raise ValueError("local provider must be ollama or lmstudio")
        args += ["--oss", "--local-provider", backend, "-c", "model_provider=" + json.dumps(backend)]
    args += ["exec"]
    if resume:
        args += ["resume"]
    args += ["--json", "--skip-git-repo-check"]
    if model:
        args += ["--model", model]
    if resume:
        args += [resume]
    return args + [prompt]


class CodexEvents:
    def __init__(self):
        self.session_id, self.final, self.error = "", "", ""
        self.completed, self.usage = False, {}
        self.failed = False

    def consume(self, event):
        kind = event.get("type")
        if kind == "thread.started":
            self.session_id = event.get("thread_id") or ""
            return [{"type": "system", "subtype": "init", "session_id": self.session_id, "model": "codex"}]
        if kind in ("error", "turn.failed"):
            self.failed = self.failed or kind == "turn.failed"
            err = event.get("error") or event.get("message") or event
            self.error = err if isinstance(err, str) else json.dumps(err)
            return [{"type": "result", "is_error": True, "result": self.error}]
        if kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                self.final = item.get("text") or ""
                return [{"type": "assistant", "message": {"content": [{"type": "text", "text": self.final}]}}]
            if item.get("type") == "command_execution":
                return [{"type": "user", "message": {"content": [{"type": "tool_result", "content": item.get("aggregated_output", "")}]}}]
        if kind == "turn.completed":
            self.completed = True
            if not self.failed:
                self.error = ""  # Native retry notices may precede a recovered turn.
            self.usage = event.get("usage") or {}
            return [{"type": "result", "is_error": bool(self.error), "result": self.error or self.final,
                     "usage": self.usage, "session_id": self.session_id}]
        return []
