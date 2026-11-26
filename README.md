# agentic-bench-tasks

**Hard, verifiable software-engineering tasks for evaluating AI coding agents**, built in the
Terminal-Bench / Harbor task format: a Docker environment, a natural-language instruction, a
hidden verifier, and a reference solution.

Every task here is original and comes with a *shortcut baseline* — the fix a fast but
careless agent typically writes — and the hidden tests are designed so that the shortcut
**fails** while a correct engineering solution **passes**.

[![validate-tasks](https://github.com/rishabhjha91/agentic-bench-tasks/actions/workflows/validate.yml/badge.svg)](https://github.com/rishabhjha91/agentic-bench-tasks/actions/workflows/validate.yml)

## Tasks

| Task | Domain | What makes it hard | Hidden tests |
|------|--------|--------------------|-------------:|
| [`sqlite-migration-runner`](tasks/sqlite-migration-runner/instruction.md) | databases | atomic migrations in SQLite (`executescript` auto-commits), trigger bodies with `;`, checksum drift vs line endings, out-of-order versions | 14 |
| [`rotating-log-follower`](tasks/rotating-log-follower/instruction.md) | systems / files | exactly-once line delivery across rename + copytruncate rotation, double rotation, partial lines, atomic state | 13 |
| [`cron-next-fire-dst`](tasks/cron-next-fire-dst/instruction.md) | time / scheduling | Vixie cron OR rule, DST gaps and overlaps, hourly vs daily fall-back semantics, never-matching expressions | 23 |

## Validation results

```
task                           agent     result expected
sqlite-migration-runner        none      fail   fail     [ok] 8 failed, 6 passed
sqlite-migration-runner        baseline  fail   fail     [ok] 4 failed, 10 passed
sqlite-migration-runner        oracle    pass   pass     [ok] 14 passed
rotating-log-follower          none      fail   fail     [ok] 9 failed, 4 passed
rotating-log-follower          baseline  fail   fail     [ok] 4 failed, 9 passed
rotating-log-follower          oracle    pass   pass     [ok] 13 passed
cron-next-fire-dst             none      fail   fail     [ok] 13 failed, 10 passed
cron-next-fire-dst             baseline  fail   fail     [ok] 3 failed, 20 passed
cron-next-fire-dst             oracle    pass   pass     [ok] 23 passed
```

The baselines pass most tests on purpose: they are good-looking fixes that only break on
the faulty assumption each task is built around. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Layout

```
tasks/<name>/
  instruction.md          # what the agent sees
  task.toml               # metadata, timeouts, resources
  environment/Dockerfile  # agent sandbox; tests are NOT copied in
  environment/app/        # starting code
  solution/solve.sh       # oracle (reference) solution
  tests/test.sh           # verifier entrypoint
  tests/test_outputs.py   # hidden tests, one per stated requirement
baselines/<name>/solve.sh # plausible shortcut that must fail
scripts/run_local.py      # none / baseline / oracle matrix, flake detection
scripts/run_docker.sh     # run the verifier inside the task image
```

## Run it

```bash
pip install pytest
python scripts/run_local.py --repeats 3          # all tasks, flake check
python scripts/run_local.py cron-next-fire-dst   # one task
scripts/run_docker.sh sqlite-migration-runner oracle
```

## Related work

This repo is one part of a small toolkit for evaluating AI coding agents:

| Repo | Role |
|------|------|
| [agentic-bench-tasks](https://github.com/rishabhjha91/agentic-bench-tasks) | original Terminal-Bench / Harbor-format tasks with hidden tests and shortcut baselines |
| [bench-task-validator](https://github.com/rishabhjha91/bench-task-validator) | `taskcheck`: quality gates a task must pass before it enters a benchmark |
| [agent-trajectory-auditor](https://github.com/rishabhjha91/agent-trajectory-auditor) | `trajaudit`: audits what an agent actually did while solving a task |

Typical flow: author a task in **agentic-bench-tasks** → gate it with **taskcheck** → run agents →
audit their trajectories with **trajaudit**.

## Author

**Rishabh Jha** — AI Evaluation & Benchmark Task Engineer (Terminal-Bench 4.0, SWE-bench-style tasks, LLM & agent evaluation)
[LinkedIn](https://www.linkedin.com/in/rishabh-jha-bbab5445/) · [GitHub](https://github.com/rishabhjha91) · rishabhinfy91@gmail.com

License: MIT. The tasks carry a canary GUID; please keep them out of training data.
