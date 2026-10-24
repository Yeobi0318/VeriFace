"""VeriFace - local face authentication for your own machine.

A privacy-first, research/educational tool that authenticates *you* against a
locally stored, DPAPI-encrypted face template. Nothing leaves the machine; the
camera and AI model are only loaded while a recognition session is running.
"""

from .version import __version__, APP_NAME

__all__ = ["__version__", "APP_NAME"]
