# Contributing to Steward

Steward uses Python 3.9 or later and the standard library. Keep provider ownership explicit and state separate from installed code.

```sh
git clone https://github.com/cmills-dev/steward.git
cd steward
python3 scripts/test_all.py
python3 scripts/build_release.py
```

The tests use temporary state and fake provider CLIs. They need no accounts or paid calls. Check paths with spaces and native Windows behaviour when changing process or file handling.

1. Branch from main and keep the change focused.
2. Add checks for changed behaviour, especially failure paths and concurrent operations.
3. Update the README and configuration example when commands or limits change.
4. Open a pull request explaining the resulting behaviour and verification.

For bug reports, include a redacted `steward report ID` and the relevant error. Logs may contain task content, private paths and tool output. Review them before sharing.

Claude defaults to bypassPermissions for unattended work. Report security issues privately through GitHub security advisories.
