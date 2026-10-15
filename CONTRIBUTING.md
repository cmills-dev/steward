# Contributing to Steward

Thanks for taking a look. Steward is small on purpose: three standard-library Python files and a status line sensor.

## Ground rules

- Python 3.9 or later, standard library only. A change that adds a dependency will not be merged.
- Nothing personal in the code. Paths, zones, binaries and thresholds come from environment variables (see `steward_config.py` and `.env.example`).
- Every behaviour change comes with a check in the matching selftest.

## Set up and test

```bash
git clone https://github.com/Cameron0404/steward.git
cd steward
./run_tests.sh
```

The selftests use a temporary `STEWARD_HOME` and never launch a session, so they need no Claude account. `STEWARD_LIVE=1 ./run_tests.sh` adds one real Haiku run that costs a few cents. To exercise the manager by hand for free, point `STEWARD_CLAUDE` at `examples/fake-claude`.

## Making a change

1. Open an issue first for anything larger than a bug fix, so the direction is agreed before you write code.
2. Branch from `main`, keep the change focused, and run `./run_tests.sh` until it prints `ALL PASS`.
3. Update the README if a command, a variable or an exit code changes, and `.env.example` if a variable is added.
4. Open a pull request that says what changed and why, and how you checked it.

## Reporting a bug

Include the output of `python3 agentctl.py report <id>` and the contents of `runs/<id>/crash.md` if it exists. Remove anything private first, such as file paths, repository names and tokens. The log can contain whatever the agent printed.

## Security

Runs default to `bypassPermissions`. If you find a way for a brief or a log to cause something outside the run's working directory, open a private security advisory on GitHub rather than a public issue.
