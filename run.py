"""Top-level launcher.

Lets you start the app with `python run.py` and gives PyInstaller a clean entry
point that imports the package normally (so the package-relative imports inside
pk_tracker work both from source and when frozen).
"""

from pk_tracker.app import main

if __name__ == "__main__":
    raise SystemExit(main())
