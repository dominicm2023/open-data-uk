"""No module of ours may carry a standard-library name.

Every script here runs as `python families/x.py` or `python scripts/x.py`,
which puts that directory first on sys.path — ahead of the standard
library. A file called platform.py in families/ was then what `import
platform` found from inside pandas, and the nightly's air family died
with "module 'platform' has no attribute 'python_implementation'" before
the traceback could say which of our files was to blame. This check says
so on the laptop, before the file reaches the box.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("", "families", "scripts")


def check_names() -> int:
    stdlib = set(sys.stdlib_module_names)
    bad = 0
    for d in DIRS:
        for p in sorted((ROOT / d).glob("*.py")):
            if p.stem in stdlib:
                print(f"FAIL  {p.relative_to(ROOT)} shadows the standard library module {p.stem!r}")
                bad += 1
    if not bad:
        print(f"PASS  no module in {', '.join(d or '.' for d in DIRS)} shadows a standard-library name")
    return bad


def main() -> int:
    failures = check_names()
    print()
    print("all module names are safe" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
