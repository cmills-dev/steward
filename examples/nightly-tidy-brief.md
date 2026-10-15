# Example brief: a small overnight chore

Queue this for the night: `python3 stewardq.py add --at tonight --title "Nightly tidy" --file examples/nightly-tidy-brief.md`

**Repo: ~/code/example-project**

Goal: remove dead code the linter already flags, without changing behaviour.

1. Run the linter and list the unused imports and unused variables it reports.
2. Remove them one file at a time, running the test suite after each file.
3. If a test fails, restore that file and note it in your checkpoint.
4. Commit on a branch named `chore/nightly-tidy`.

Write your checkpoint as you go: Done, In progress, Next, Files touched, How to verify.
Your report: the files changed, the test result, and anything you skipped and why.
