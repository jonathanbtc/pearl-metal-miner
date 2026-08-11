#!/usr/bin/env python3
"""Check for the A6 --help contract (issue #25).

Three assertions: every flag carries help text; --help alone contains the
path from nothing to mining (wallet creation, self-test, a run) plus the
PRL_RAW contributor pointer; and every flag the parser knows appears in the
README (the flags table and --help must not drift apart).

    .venv/bin/python tools/check_help.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def check_all_flags_documented() -> bool:
    from pearl_metal_miner.miner import build_parser
    bare = [a.option_strings for a in build_parser()._actions if not a.help]
    if bare:
        print(f"FAIL coverage: flags without help text: {bare}")
        return False
    default_pool = build_parser().get_default("pool")
    if default_pool != "luckypool":  # the pool with verified accepted shares
        print(f"FAIL coverage: default pool is {default_pool!r}, not luckypool")
        return False
    print("PASS coverage: every flag has help text; default pool is luckypool")
    return True


def check_help_output() -> bool:
    r = subprocess.run([sys.executable, "-m", "pearl_metal_miner.miner",
                        "--help"], capture_output=True, text=True, cwd=ROOT)
    needles = ["wallet new", "--self-test", "wallet {new,show,verify}",
               "PRL_RAW=1", "hobby, not an income", "Ctrl-C",
               "python -m pearl_metal_miner.miner"]
    missing = [n for n in needles if n not in r.stdout]
    if r.returncode != 0 or missing:
        print(f"FAIL help: rc={r.returncode}, missing {missing}\n{r.stdout}")
        return False
    print("PASS help: nothing-to-mining path, siblings, and PRL_RAW present")
    return True


def check_readme_agreement() -> bool:
    from pearl_metal_miner.miner import build_parser
    with open(os.path.join(ROOT, "README.md")) as f:
        readme = f.read()
    flags = [a.option_strings[0] for a in build_parser()._actions
             if a.option_strings and a.option_strings[0] != "-h"]
    missing = [f for f in flags if f not in readme]
    if missing:
        print(f"FAIL readme: flags absent from README: {missing}")
        return False
    print(f"PASS readme: all {len(flags)} flags appear in the README")
    return True


def main() -> int:
    ok = check_all_flags_documented()
    ok = check_help_output() and ok
    ok = check_readme_agreement() and ok
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
