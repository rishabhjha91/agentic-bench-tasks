# How these tasks are built

Each task follows the same pipeline I use for benchmark work.

## 1. Pick a real behaviour gap, not a puzzle
The starting code in `environment/app` is the kind of code that ships: it works on the
happy path and has the bugs real systems have (non-atomic migrations, offset-only log
tailing, naive DST handling). The instruction is written like an incident report from a
teammate: what was seen, and the contract the fix must keep.

## 2. Write the contract, then the hidden tests
Every hidden test maps to one sentence of `instruction.md`. Nothing is tested that the
instruction does not state, so a correct solution never fails on an unstated rule.

## 3. Aim tests at faulty assumptions
The hardest tests target the assumptions an agent makes when it takes a shortcut:

| Task | Assumption a shortcut makes | What the test checks |
|------|-----------------------------|----------------------|
| sqlite-migration-runner | `executescript` inside try/rollback is transactional | half-applied migration leaves no table behind |
| sqlite-migration-runner | splitting SQL on `;` is fine | trigger bodies and string literals containing `;` |
| sqlite-migration-runner | hashing raw bytes is a fine checksum | CRLF/LF conversion is not drift |
| rotating-log-follower | "file got smaller" detects rotation | new file already larger than old offset |
| rotating-log-follower | on rotation, just switch to the new file | tail of the rotated file is drained first, across two rotations |
| rotating-log-follower | writing JSON in place is safe | crash mid-save leaves the old state intact |
| cron-next-fire-dst | walk minutes and compare wall-clock time | spring-forward time fires once at the jump; fall-back fires once (daily) or twice (hourly) |
| cron-next-fire-dst | day-of-month AND day-of-week | Vixie OR rule when both are restricted |

## 4. Prove the task discriminates
`scripts/run_local.py` runs three agents per task and the task is only valid when:

* **none** (untouched environment) fails,
* **baseline** (a plausible shortcut in `baselines/`) fails,
* **oracle** (`solution/solve.sh`) passes, deterministically, across repeated runs.

CI runs this on every push, plus the verifier inside each task's Docker image with the
network disabled.

## 5. Keep the benchmark clean
* Tests and solutions are never copied into the agent's image.
* Every task folder carries a canary string so the content can be filtered out of
  training corpora.
* Instructions never name the solution technique (`complete_statement`, `st_ino`, `fold`),
  only the observable behaviour.
