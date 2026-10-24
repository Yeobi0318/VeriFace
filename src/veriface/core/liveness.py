"""Lightweight liveness / anti-spoofing.

A face-auth system that a printed photo can defeat is worse than useless, so
VeriFace asks for a small active challenge (a head turn or nod) and checks for
natural motion plus image texture before accepting a match.

This is an honest, basic presentation-attack defence suitable for a personal /
research tool - it raises the bar well above "hold up a photo", but it is *not*
a certified anti-spoofing solution (it will not reliably stop a high-quality
video replay). The README states this plainly.

Landmark layout in a YuNet row (columns 4..13):
    right-eye, left-eye, nose-tip, right-mouth, left-mouth  (x, y pairs)
"""
from __future__ import annotations

import math


class LivenessTracker:
    TURN_RANGE = 0.22     # required left<->right swing of the nose/eye ratio
    NOD_RANGE = 0.18      # required up<->down swing (fraction of eye distance)
    MOTION_MIN = 0.0015   # min positional variance to call it "not a still photo"

    def __init__(self, challenge: str = "turn", min_sharpness: float = 45.0) -> None:
        self.challenge = challenge
        self.min_sharpness = float(min_sharpness)
        self._yaw: list[float] = []
        self._pitch: list[float] = []
        self._sharpness_best = 0.0
        self._samples = 0

    def update(self, det, aligned) -> None:
        import numpy as np
        import cv2

        row = det.row.flatten()
        rex, rey, lex, ley = row[4], row[5], row[6], row[7]
        nx, ny = row[8], row[9]
        eye_mid_x = (rex + lex) / 2.0
        eye_mid_y = (rey + ley) / 2.0
        eye_dist = math.hypot(lex - rex, ley - rey) or 1.0

        # Normalised nose offset from the eye midpoint -> pose proxies.
        self._yaw.append((nx - eye_mid_x) / eye_dist)
        self._pitch.append((ny - eye_mid_y) / eye_dist)

        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        self._sharpness_best = max(
            self._sharpness_best, float(cv2.Laplacian(gray, cv2.CV_64F).var())
        )
        self._samples += 1

    # -- metrics ----------------------------------------------------------
    @staticmethod
    def _rng(vals: list[float]) -> float:
        return (max(vals) - min(vals)) if vals else 0.0

    @staticmethod
    def _var(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / len(vals)
        return sum((v - m) ** 2 for v in vals) / len(vals)

    def progress(self) -> float:
        """0..1 progress toward satisfying the active challenge (for the UI)."""
        if self.challenge == "nod":
            return min(1.0, self._rng(self._pitch) / self.NOD_RANGE)
        if self.challenge == "motion":
            return min(1.0, self._var(self._yaw) / self.MOTION_MIN)
        return min(1.0, self._rng(self._yaw) / self.TURN_RANGE)

    def hint(self) -> str:
        return {
            "turn": "Slowly turn your head left, then right",
            "nod": "Slowly nod your head up and down",
            "motion": "Look at the camera and move slightly",
        }.get(self.challenge, "Move your head slightly")

    def passed(self) -> tuple[bool, str]:
        if self._samples < 5:
            return False, "Need more frames"
        if self._sharpness_best < self.min_sharpness:
            return False, "Image too flat (possible photo/screen); move closer in good light"
        if self._var(self._yaw) < self.MOTION_MIN and self.challenge != "nod":
            return False, "No natural motion detected"
        if self.progress() < 1.0:
            return False, self.hint()
        return True, "Liveness OK"
