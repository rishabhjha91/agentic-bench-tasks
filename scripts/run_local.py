#!/usr/bin/env python3
"""Run every task's verifier locally (no Docker) against three agents:

* ``none``     – the untouched starting environment (must FAIL)
* ``baseline`` – a plausible shortcut fix in baselines/<task>/solve.sh (must FAIL)
* ``oracle``   – the reference solution in tasks/<task>/solution/solve.sh (must PASS)

A task is only "good" when that whole pattern holds; this is the same check a
reviewer does before a task is accepted into a benchmark.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECT = {"none": False, "baseline": False, "oracle": True}


def run_task(task: Path, agent: str, repeats: int = 1) -> tuple[bool, str]:
    results = []
    for _ in range(repeats):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            shutil.copytree(task / "environment" / "app", app)
            env = {**os.environ, "APP_DIR": str(app), "PYTHONDONTWRITEBYTECODE": "1"}
            script = None
            if agent == "oracle":
                script = task / "solution" / "solve.sh"
            elif agent == "baseline":
                script = ROOT / "baselines" / task.name / "solve.sh"
            if script is not None:
                subprocess.run(["bash", str(script)], env=env, check=True, cwd=app)
            proc = subprocess.run(["bash", str(task / "tests" / "test.sh")], env=env,
                                  cwd=app, capture_output=True, text=True, timeout=600)
            summary = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
            results.append((proc.returncode == 0, summary))
    passed = {r[0] for r in results}
    if len(passed) > 1:
        return False, "FLAKY: " + " | ".join(s for _, s in results)
    return results[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="*", help="task names (default: all)")
    ap.add_argument("--repeats", type=int, default=1, help="re-run each agent N times to catch flaky tests")
    args = ap.parse_args()
    tasks = sorted(p for p in (ROOT / "tasks").iterdir() if p.is_dir())
    if args.tasks:
        tasks = [t for t in tasks if t.name in args.tasks]
    ok_all = True
    print(f"{'task':<30} {'agent':<9} {'result':<6} {'expected':<8} summary")
    for task in tasks:
        for agent, want in EXPECT.items():
            passed, summary = run_task(task, agent, args.repeats)
            good = passed == want and not summary.startswith("FLAKY")
            ok_all &= good
            mark = "ok" if good else "BAD"
            print(f"{task.name:<30} {agent:<9} {'pass' if passed else 'fail':<6} "
                  f"{'pass' if want else 'fail':<8} [{mark}] {re.sub(r'\s+', ' ', summary)}")
    print("\nALL TASKS VALID" if ok_all else "\nSOME TASKS INVALID")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
