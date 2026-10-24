"""Run VeriFace from source: ``python run.py`` (GUI) or ``python run.py auth``."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from veriface.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
