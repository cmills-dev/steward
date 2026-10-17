"""Transfer task checkpoints without copying credentials or provider session stores."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import agentctl as A
from steward_lock import file_lock
import steward_provider as P

FILES = {"brief.md", "progress.md", "notes.md"}
LIMIT = 5 * 1024 * 1024


def export_run(rid, output):
    state = A.load_state(rid)
    if not state:
        raise ValueError("unknown run: " + rid)
    if state.get("status") in ("running", "starting"):
        raise ValueError("pause the run and wait for it to stop before exporting")
    files = {name: (A.run_dir(rid) / name).read_bytes() for name in FILES if (A.run_dir(rid) / name).is_file()}
    if "brief.md" not in files or "progress.md" not in files:
        raise ValueError("a portable task needs both brief.md and progress.md")
    meta = {"schema": 1, "source_id": rid, "provider": state.get("provider", "claude"),
            "model": state.get("model", ""), "project": state.get("project", ""), "tags": state.get("tags", []),
            "local_provider": state.get("local_provider", ""), "max_minutes": state.get("max_minutes", 90),
            "hashes": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if sum(map(len, files.values())) > LIMIT:
        raise ValueError("checkpoint bundle exceeds 5 MiB")
    output = Path(output).expanduser().resolve()
    with output.open("xb") as f:
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("portable.json", json.dumps(meta, indent=2))
            for name, data in files.items():
                z.writestr(name, data)
    print("Exported %s. Review its brief and notes before sharing.\n"
          "Project files, credentials and native conversations are excluded." % output)


def import_run(bundle, rid, repo, provider_override=None, model_override=None, local_override=None):
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("--repo must name an existing project directory")
    dest = A.run_dir(rid)
    with zipfile.ZipFile(bundle) as z:
        infos = z.infolist()
        names = {i.filename for i in infos}
        if len(names) != len(infos) or names - (FILES | {"portable.json"}) or not {"portable.json", "brief.md", "progress.md"} <= names:
            raise ValueError("invalid bundle members")
        if sum(i.file_size for i in infos) > LIMIT:
            raise ValueError("bundle exceeds 5 MiB")
        meta = json.loads(z.read("portable.json"))
        if not isinstance(meta, dict) or meta.get("schema") != 1:
            raise ValueError("unsupported bundle schema")
        provider = P.validate(meta.get("provider"))
        P.metadata(meta.get("project", ""), meta.get("tags", []))
        for key in ("model", "source_id", "local_provider"):
            if not isinstance(meta.get(key, ""), str) or len(meta.get(key, "")) > 200:
                raise ValueError("invalid bundle metadata: " + key)
        if not isinstance(meta.get("max_minutes", 90), int) or not 1 <= meta.get("max_minutes", 90) <= 10080:
            raise ValueError("max_minutes must be 1 to 10080")
        if provider == "local" and meta.get("local_provider") not in ("ollama", "lmstudio"):
            raise ValueError("invalid local provider")
        if not isinstance(meta.get("hashes"), dict):
            raise ValueError("invalid bundle hashes")
        data = {n: z.read(n) for n in names & FILES}
        if set(meta.get("hashes", {})) != set(data) or any(hashlib.sha256(v).hexdigest() != meta["hashes"][n] for n, v in data.items()):
            raise ValueError("bundle checksum mismatch")
    source_provider = provider
    provider = P.validate(provider_override or provider)
    model = model_override if model_override is not None else (meta.get("model", "") if provider == source_provider else "")
    model = P.model_for(provider, model)
    engine = local_override or (meta.get("local_provider") if source_provider == "local" else "") or "ollama"
    with file_lock(A.HEALTH / "admission.lock"):
        if dest.exists():
            raise ValueError("run id already exists: " + rid)
        dest.mkdir(parents=True, mode=0o700)
        for name, content in data.items():
            (dest / name).write_bytes(content)
        A.save_state(rid, id=rid, status="imported", provider=provider, model=model,
            project=meta.get("project", ""), tags=meta.get("tags", []), local_provider=engine if provider == "local" else "",
            max_minutes=int(meta.get("max_minutes", 90)), session_id="", cwd=str(repo), repo=str(repo),
            brief=str(dest / "brief.md"), source_id=meta.get("source_id", ""), source_provider=source_provider,
            reason="portable checkpoint imported; resume starts a new native conversation")
    print("Imported %s. Project: %s. Provider: %s.\nResume with: steward resume %s" % (rid, meta.get("project", ""), provider, rid))


def main(command, args):
    p = argparse.ArgumentParser(prog="steward " + command)
    if command == "export":
        p.add_argument("id")
        p.add_argument("--output", required=True)
        a = p.parse_args(args)
        export_run(a.id, a.output)
    else:
        p.add_argument("bundle")
        p.add_argument("--id", required=True)
        p.add_argument("--repo", required=True)
        p.add_argument("--provider", choices=P.PROVIDERS, help="Explicitly hand the checkpoint to another provider")
        p.add_argument("--model", help="Destination provider's model")
        p.add_argument("--local-provider", choices=("ollama", "lmstudio"))
        a = p.parse_args(args)
        import_run(a.bundle, a.id, a.repo, a.provider, a.model, a.local_provider)
    return 0
