"""Entry point: ``python -m veriface`` and the packaged VeriFace.exe.

Two things that specifically matter for the frozen (PyInstaller) build:

* **Absolute imports.** PyInstaller runs this file as the top-level ``__main__``
  module with no package context, so relative imports (``from .app ...``) raise
  ``ImportError``. We import the package absolutely (``from veriface.app ...``),
  which works both frozen and under ``python -m veriface``.
* **No stdout/stderr in a windowed build.** A ``console=False`` exe has
  ``sys.stdout``/``sys.stderr`` set to ``None``; any ``print()`` or ``.write()``
  then throws. We redirect them to the null device and report fatal errors with
  a GUI message box instead of writing to a stream that does not exist.
"""
from __future__ import annotations

import os
import sys


def _ensure_std_streams() -> None:
    """Make stdout/stderr safe to use even in a windowed PyInstaller build."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _report_error(title: str, message: str) -> None:
    """Show a fatal error in a dialog (works with no console) and log it."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        try:
            sys.stderr.write(message + "\n")
        except Exception:
            pass
    _log(message)


def _log(message: str) -> None:
    try:
        from veriface.core import paths

        paths.ensure_dirs()
        with open(paths.LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except Exception:
        pass


def main() -> int:
    _ensure_std_streams()
    argv = sys.argv[1:]

    if not argv or argv == ["gui"]:
        try:
            from veriface.app import main as gui_main

            gui_main()
            return 0
        except Exception:
            import traceback

            _report_error("VeriFace failed to start", traceback.format_exc())
            return 1

    try:
        from veriface.cli import main as cli_main

        return cli_main(argv)
    except Exception:
        import traceback

        _report_error("VeriFace", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
