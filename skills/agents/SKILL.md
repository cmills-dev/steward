---
name: agents
description: Run, watch, pause, resume and transfer managed Claude, Codex and local-model tasks with Steward.
---

# Managed agents

Use the installed `steward` command, or `python3 /path/to/steward_cli.py`. Read the project's own instructions before launching a task. Choose an existing project directory and write a brief with a goal and verification steps.

- Start: `steward run --id ID --provider claude|codex|local --brief brief.md --repo DIR --project NAME --tag TAG`.
- Local runs require an explicit installed `--model` and an Ollama or LM Studio server through Codex.
- Queue: `steward queue add --at tonight --title TITLE --file brief.md --provider PROVIDER --repo DIR`.
- Dispatch: keep `steward watch` running on an awake machine, or schedule `steward queue tick` externally.
- Inspect: `steward status`, `steward logs ID --follow`, `steward report ID`.
- Pause: `steward pause ID`. Wait for it to stop before transferring.
- Resume: `steward resume ID`. The saved provider owns the native conversation.
- Stop: `steward kill ID` records an outcome.
- Transfer: `steward export ID --output task.zip`, copy project files separately, then `steward import task.zip --id NEW_ID --repo DIR`. Resume starts a fresh conversation from the checkpoint.

Keep checkpoints current. Record facts, changed files, remaining work and how to verify. Put operator notes in the run's notes.md. Review logs and bundles for private content before sharing.

Claude supports status-line quota wind-down, context rotation, a dollar cap and a Claude-only fallback ladder. Codex and local adapters retain token counts where emitted but report dollar cost as unknown. They use a wall-time cap and have no enforced dollar cap. A missing quota sensor cannot provide proactive quota protection.
