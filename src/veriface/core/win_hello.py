"""Helpers for the Windows Hello Face integration path.

Why this module exists instead of a credential provider / browser hook:

Getting *face* in place of the PIN for (a) the Windows sign-in screen and
(b) Chrome's "Verify it's you" password prompt is already solved by
**Windows Hello Face**:

* The OS sign-in uses whichever Hello method is enrolled - set up Face and the
  lock screen recognises you instead of asking for the PIN. (Windows keeps the
  PIN as a mandatory recovery fallback by design; it cannot be fully removed
  while Hello is on, which is a good thing - it is your lockout insurance.)
* Chrome's *Use Windows Hello when filling passwords* routes its verification
  through Hello, so once Face is enrolled, Chrome reveals/fills passwords after
  recognising your face - no PIN typing.

VeriFace therefore does NOT replace the logon (that needs an unsigned custom
credential provider - a lockout and security risk) and does NOT touch Chrome's
password store or process. It detects whether this device can do Hello Face and
opens the right settings pages. This is the supported, secure way to get exactly
the behaviour requested.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class HelloStatus:
    cameras: list[str] = field(default_factory=list)
    ir_cameras: list[str] = field(default_factory=list)
    hello_face_capable: bool = False
    note: str = ""


_CREATE_NO_WINDOW = 0x08000000  # keep PowerShell from flashing a console


def _ps(cmd: str, timeout: int = 10) -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def detect() -> HelloStatus:
    """Best-effort check for Windows Hello Face capability (needs an IR camera)."""
    cams: list[str] = []
    out = _ps("Get-PnpDevice -Class Camera -Status OK -ErrorAction SilentlyContinue | "
              "Select-Object -ExpandProperty FriendlyName")
    for ln in out.splitlines():
        ln = ln.strip()
        if ln and ln not in cams:
            cams.append(ln)

    ir = [c for c in cams if ("ir" in c.lower().split() or "infrared" in c.lower()
                              or " ir " in f" {c.lower()} " or c.lower().endswith(" ir"))]

    status = HelloStatus(cameras=cams, ir_cameras=ir, hello_face_capable=bool(ir))
    if ir:
        status.note = ("IR camera detected - this device can use Windows Hello "
                       "Face. Set it up in sign-in settings below.")
    elif cams:
        status.note = ("No IR camera detected. Windows Hello Face normally needs "
                       "an IR camera, so OS face-login may be unavailable here; "
                       "VeriFace's own in-app face unlock still works.")
    else:
        status.note = ("No camera detected. Connect a webcam (an IR one for "
                       "Windows Hello Face).")
    return status


def open_signin_settings() -> None:
    """Open Settings > Accounts > Sign-in options (where Hello Face is set up)."""
    subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:signinoptions"],
                     creationflags=_CREATE_NO_WINDOW)


def open_chrome_password_settings() -> None:
    """Open Chrome's password settings so the Hello toggle can be enabled."""
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "chrome",
                          "chrome://settings/passwords"],
                         creationflags=_CREATE_NO_WINDOW)
    except OSError:
        pass
