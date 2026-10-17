"""End-to-end portable installation, provider ownership and transfer checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class Portable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="steward test ")
        self.base = Path(self.tmp.name)
        self.work = self.base / "sample project"
        self.work.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("STEWARD_", "FAKE_", "DEMO_"))}
        self.env.update(STEWARD_HOME=str(self.base / "state"), STEWARD_WORKDIR=str(self.work),
            STEWARD_CLAUDE=str(ROOT / "examples/fake-claude"), STEWARD_CODEX=str(ROOT / "examples/fake-codex.py"),
            FAKE_LOG=str(self.base / "argv.jsonl"))

    def tearDown(self):
        # A detached worker moves its entry before interpreter shutdown closes its
        # redirected log handle. Windows cannot unlink that handle while it exits.
        deadline = time.monotonic() + 3
        while True:
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)

    def cli(self, *args, env=None, code=0):
        p = subprocess.run([sys.executable, str(ROOT / "steward_cli.py"), *args], env=env or self.env,
                           cwd=self.work, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        return p

    def run_agent(self, rid="task", provider="codex", **kwargs):
        return self.cli("run", "--id", rid, "--provider", provider, "--model", "qwen-local" if provider == "local" else "gpt-6.1-sol" if provider == "codex" else "sonnet",
            "--brief", str(ROOT / "examples/hello-brief.md"), "--repo", str(self.work),
            "--project", "demo", "--tag", "research", **kwargs)

    def state(self, rid="task"):
        return json.loads((self.base / "state/runs" / rid / "state.json").read_text())

    def test_install_and_free_demo_away_from_checkout(self):
        prefix = self.base / "installed copy"
        p = subprocess.run([sys.executable, str(ROOT / "install.py"), "--prefix", str(prefix)],
            env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        runtime = prefix / "share/steward" / (ROOT / "VERSION").read_text().strip()
        cli = [sys.executable, str(runtime / "steward_cli.py")]
        for args in [["init"], ["demo"], ["doctor", "--json"]]:
            result = subprocess.run(cli + args, env=self.env, cwd=self.work, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((runtime / ".git").exists())
        self.assertTrue((prefix / ("bin/steward.cmd" if os.name == "nt" else "bin/steward")).is_file())

    def test_codex_resume_keeps_owner_and_thread(self):
        self.run_agent()
        before = self.state()
        env = dict(self.env, STEWARD_PROVIDER="claude")
        self.cli("resume", "task", "--force", env=env)
        after = self.state()
        self.assertEqual(after["provider"], "codex")
        self.assertEqual(after["session_id"], before["session_id"])
        self.assertEqual(after["status"], "done")
        self.assertFalse(after["cost_known"])
        self.assertEqual(after["token_usage"]["input_tokens"], 20)

    def test_local_keeps_engine_on_resume(self):
        self.run_agent(provider="local")
        self.cli("resume", "task", "--force", env=dict(self.env, STEWARD_LOCAL_PROVIDER="lmstudio"))
        args = json.loads((self.base / "argv.jsonl").read_text().splitlines()[-1])
        self.assertEqual(args[args.index("--local-provider") + 1], "ollama")
        self.assertEqual(self.state()["provider"], "local")
        self.assertIn("--oss", args)

    def test_missing_or_error_completion_is_failed(self):
        for mode in ["empty", "error"]:
            self.run_agent(mode, env=dict(self.env, FAKE_MODE=mode), code=1)
            self.assertEqual(self.state(mode)["status"], "failed")

    def test_native_retry_can_recover_but_failed_turn_cannot(self):
        sys.path.insert(0, str(ROOT))
        from steward_provider import CodexEvents
        events = CodexEvents()
        events.consume({"type": "error", "message": "Reconnecting... 1/5"})
        events.consume({"type": "item.completed", "item": {"type": "agent_message", "text": "Complete"}})
        events.consume({"type": "turn.completed", "usage": {}})
        self.assertFalse(events.error)
        events.consume({"type": "turn.failed", "error": {"message": "failed"}})
        events.consume({"type": "turn.completed", "usage": {}})
        self.assertTrue(events.error)

    def test_provider_mismatch_cannot_overwrite_run(self):
        self.run_agent()
        before = self.state()
        self.run_agent(provider="claude", code=2)
        self.assertEqual(self.state()["session_id"], before["session_id"])

    def test_tags_filter_projects(self):
        self.run_agent()
        self.assertIn("task", self.cli("status", "--project", "demo", "--tag", "research").stdout)
        self.assertIn("no agent runs", self.cli("status", "--project", "other").stdout)

    def test_transfer_starts_new_native_conversation(self):
        self.run_agent()
        sid = self.state()["session_id"]
        bundle = self.base / "task.zip"
        self.cli("export", "task", "--output", str(bundle))
        with zipfile.ZipFile(bundle) as z:
            self.assertNotIn(sid, z.read("portable.json").decode())
            self.assertEqual(set(z.namelist()), {"portable.json", "brief.md", "progress.md"})
        self.cli("import", str(bundle), "--id", "transferred", "--repo", str(self.work))
        self.assertEqual(self.state("transferred")["status"], "imported")
        self.cli("resume", "transferred")
        state = self.state("transferred")
        self.assertEqual(state["provider"], "codex")
        self.assertNotEqual(state["session_id"], sid)
        self.assertEqual(state["tags"], ["research"])

    def test_transfer_rejects_unsafe_members(self):
        bundle = self.base / "unsafe.zip"
        with zipfile.ZipFile(bundle, "w") as z:
            z.writestr("../bad", "bad")
        self.cli("import", str(bundle), "--id", "unsafe", "--repo", str(self.work), code=2)
        self.assertFalse((self.base / "state/runs/unsafe").exists())

    def test_run_id_cannot_escape_state(self):
        self.run_agent("../escape", code=2)
        self.assertFalse((self.base / "state/escape").exists())

    def test_simultaneous_launches_obey_cap(self):
        env = dict(self.env, STEWARD_MAX_CONCURRENT="1", FAKE_MODE="slow")
        args = [sys.executable, str(ROOT / "steward_cli.py"), "run", "--provider", "codex",
                "--brief", str(ROOT / "examples/hello-brief.md"), "--repo", str(self.work)]
        ps = [subprocess.Popen(args + ["--id", rid], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
              for rid in ["first", "second"]]
        outcomes = [p.communicate(timeout=20) for p in ps]
        self.assertEqual(sorted(p.returncode for p in ps), [0, 79], str(outcomes))

    def test_queue_retains_provider_and_tags(self):
        self.cli("queue", "add", "--at", "now", "--title", "research", "--file", str(ROOT / "examples/hello-brief.md"),
                 "--provider", "codex", "--project", "demo", "--tag", "research", "--repo", str(self.work))
        self.cli("queue", "tick")
        for _ in range(150):
            states = list((self.base / "state/runs").glob("*/state.json"))
            if states and json.loads(states[0].read_text()).get("status") == "done":
                break
            time.sleep(.05)
        else:
            self.fail("queued run did not finish")
        state = json.loads(states[0].read_text())
        self.assertEqual((state["provider"], state["project"], state["tags"]), ("codex", "demo", ["research"]))
        for _ in range(60):
            if not list((self.base / "state/queue/pending").glob("*.md")):
                break
            time.sleep(.05)

    def test_launcher_runs_with_spaces(self):
        prefix = self.base / "installed copy"
        p = subprocess.run([sys.executable, str(ROOT / "install.py"), "--prefix", str(prefix)],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        binary = prefix / ("bin/steward.cmd" if os.name == "nt" else "bin/steward")
        p = subprocess.run([str(binary), "--version"], cwd=self.work, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Steward", p.stdout)

    def test_worker_retains_admission_refusal_but_closes_killed_work(self):
        for mode in ("refused", "killed"):
            self.cli("queue", "add", "--at", "now", "--title", mode, "--text", "task", "--provider", "codex")
            pending = next((self.base / "state/queue/pending").glob("*" + mode + "-*.md"))
            code = "import sys; sys.path.insert(0,sys.argv[1]); import steward_worker as W; "
            code += "sys.argv=['worker','run','--id',sys.argv[2]]; "
            if mode == "killed":
                code += "W.subprocess.call=lambda args: (W.A.save_state(sys.argv[3],status='killed'),79)[1]; "
            else:
                code += "W.subprocess.call=lambda args: 79; "
            code += "W.main()"
            p = subprocess.run([sys.executable, "-c", code, str(ROOT), mode],
                env=dict(self.env, STEWARD_QUEUE_SOURCE=str(pending)), capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(pending.exists(), mode == "refused")

    def test_transfer_rejects_tampering_and_invalid_metadata(self):
        self.run_agent(provider="local")
        original = self.base / "task.zip"
        self.cli("export", "task", "--output", str(original))
        with zipfile.ZipFile(original) as z:
            items = {n: z.read(n) for n in z.namelist()}
        for mode in ("content", "tags", "duration"):
            edited = dict(items)
            meta = json.loads(edited["portable.json"])
            if mode == "content":
                edited["brief.md"] += b"tampered"
            elif mode == "tags":
                meta["tags"] = {"bad": "type"}
            else:
                meta["max_minutes"] = -1
            edited["portable.json"] = json.dumps(meta)
            bundle = self.base / (mode + ".zip")
            with zipfile.ZipFile(bundle, "w") as z:
                for n, data in edited.items():
                    z.writestr(n, data)
            self.cli("import", str(bundle), "--id", mode, "--repo", str(self.work), code=2)
            self.assertFalse((self.base / "state/runs" / mode).exists())

    def test_import_preserves_local_engine(self):
        self.run_agent(provider="local")
        bundle = self.base / "task.zip"
        self.cli("export", "task", "--output", str(bundle))
        self.cli("import", str(bundle), "--id", "moved", "--repo", str(self.work))
        self.cli("resume", "moved", env=dict(self.env, STEWARD_LOCAL_PROVIDER="lmstudio"))
        self.assertEqual(self.state("moved")["local_provider"], "ollama")

    def test_explicit_checkpoint_handoff_to_another_provider(self):
        self.run_agent(provider="codex")
        bundle = self.base / "handoff.zip"
        self.cli("export", "task", "--output", str(bundle))
        self.cli("import", str(bundle), "--id", "handed-off", "--repo", str(self.work), "--provider", "claude", "--model", "sonnet")
        self.cli("resume", "handed-off")
        state = self.state("handed-off")
        self.assertEqual((state["provider"], state["source_provider"], state["tags"]), ("claude", "codex", ["research"]))
        self.assertEqual(state["status"], "done")

    def test_claude_quota_does_not_block_codex(self):
        health = self.base / "state/health"
        health.mkdir(parents=True)
        import datetime as dt
        now = dt.datetime.now().astimezone()
        (health / "usage.json").write_text(json.dumps({"_written": now.isoformat(), "data": {"rate_limits": {
            "five_hour": {"used_percentage": 100, "resets_at": (now + dt.timedelta(hours=1)).timestamp()},
            "seven_day": {"used_percentage": 100, "resets_at": (now + dt.timedelta(days=1)).timestamp()}}}}))
        self.run_agent(provider="codex")
        self.assertEqual(self.state()["status"], "done")
        self.run_agent("claude-refused", provider="claude", code=79)

    def test_archive_is_reproducible_and_installs_after_extraction(self):
        dirs = [self.base / "release one", self.base / "release two"]
        for dest in dirs:
            p = subprocess.run([sys.executable, str(ROOT / "scripts/build_release.py"), "--output", str(dest)],
                               capture_output=True, text=True, env=self.env)
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((dirs[0] / "SHA256SUMS").read_bytes(), (dirs[1] / "SHA256SUMS").read_bytes())
        archive = next(dirs[0].glob("*.zip"))
        with zipfile.ZipFile(archive) as z:
            self.assertFalse(any(".git/" in n or "/runs/" in n or "/health/" in n or n.endswith("/.env") for n in z.namelist()))
            z.extractall(self.base / "extracted")
        source = next((self.base / "extracted").iterdir())
        prefix = self.base / "archive install"
        p = subprocess.run([sys.executable, str(source / "install.py"), "--prefix", str(prefix)], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        runtime = prefix / "share/steward" / (ROOT / "VERSION").read_text().strip()
        p = subprocess.run([sys.executable, str(runtime / "steward_cli.py"), "demo"], env=self.env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
