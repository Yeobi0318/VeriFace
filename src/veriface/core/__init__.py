"""Core, GUI-independent logic for VeriFace.

Heavy third-party imports (OpenCV, numpy) live *inside* the functions that need
them, never at module import time, so that launching the GUI and running "PC
Analysis" stay instant and work even before the AI models are installed.
"""
