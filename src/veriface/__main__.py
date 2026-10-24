"""Entry point: ``python -m veriface`` and the packaged VeriFace.exe.

No-argument launch opens the GUI. If a GUI dependency is missing we fail with a
clear, actionable message instead of a raw traceback.
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    # Fast path for the GUI so a missing GUI dep gives a friendly message.
    if not argv or argv == ["gui"]:
        try:
            from .app import main as gui_main
        except ImportError as exc:
            sys.stderr.write(
                "VeriFace GUI dependencies are missing "
                f"({exc}).\n"
                "Install them with:\n    pip install customtkinter pillow\n"
            )
            return 2
        gui_main()
        return 0

    from .cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
