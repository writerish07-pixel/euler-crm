"""Run each backend test module in its own pytest process.

Every module imports `server` and shares one in-memory Mongo database, so a
module that leaves rows behind can change another module's result (scheme rows,
Price Master, counters). Running modules in separate processes makes the suite
order-independent without changing any test.

Usage (from backend/):
    python scripts/run_tests_isolated.py [-j N] [--junit-dir DIR] [extra pytest args]

Exit code is non-zero when any module fails or errors.
"""
import argparse
import concurrent.futures as cf
import glob
import os
import subprocess
import sys
import time


def modules():
    found = sorted(glob.glob("tests/test_*.py")) + sorted(glob.glob("tests/regression_claude/test_*.py"))
    return [m for m in found if os.path.isfile(m)]


def run_one(path, junit_dir, extra):
    junit = os.path.join(junit_dir, path.replace("/", "__").replace(".py", ".xml"))
    cmd = [sys.executable, "-m", "pytest", path, "-q", "--tb=line", "-p", "no:cacheprovider",
           f"--junitxml={junit}", *extra]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    # pytest exit code 5 = no tests collected (e.g. every test skipped as live_http).
    ok = proc.returncode in (0, 5)
    return path, ok, round(time.time() - t0, 1), tail[0], proc.stdout if not ok else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--junit-dir", default="test-results")
    args, extra = ap.parse_known_args()
    os.makedirs(args.junit_dir, exist_ok=True)
    mods = modules()
    failed = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for path, ok, secs, tail, out in ex.map(lambda m: run_one(m, args.junit_dir, extra), mods):
            print(f"{'PASS' if ok else 'FAIL'} {secs:7.1f}s {path}  {tail}", flush=True)
            if not ok:
                failed.append((path, out))
    for path, out in failed:
        print(f"\n===== {path} =====\n{out[-4000:]}")
    print(f"\n{len(mods) - len(failed)}/{len(mods)} modules passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
