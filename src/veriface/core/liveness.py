"""Liveness / anti-spoofing, including eye-blink detection.

A face-auth system that a printed photo can defeat is worse than useless, so
VeriFace asks for a small active challenge and checks for natural motion plus
image texture before accepting a match.

Challenges
----------
* **blink** (default)  - detect a real eye blink (open -> closed -> open).
* **turn / nod**       - a head rotation measured from the landmarks.
* **motion**           - natural micro-movement (not a still photo).

Blink detection does not rely on a landmark/EAR model (YuNet only gives 5
points, and OpenCV 5.0 dropped the Haar eye cascades). Instead it measures the
*edge energy* inside each eye region: an open eye (iris, lashes, sclera border)
has far more fine detail than a smooth closed eyelid, so edge energy dips during
a blink and recovers afterwards.

This is an honest, basic presentation-attack defence for a personal/research
tool - it beats "hold up a photo", but it is not a certified anti-spoof system
(it will not reliably stop a high-quality video replay). The About tab says so.

Status/reason codes (not sentences) are returned so the GUI can localise them.
"""
from __future__ import annotations

import math


class _BlinkDetector:
    """Tracks eye-openness over frames and counts blinks (hysteresis)."""

    CLOSE_RATIO = 0.55   # openness below this fraction of baseline -> "closed"
    OPEN_RATIO = 0.78    # back above this -> "open" again (one blink counted)
    WARMUP = 3

    def __init__(self) -> None:
        self.baseline = 0.0
        self.blinks = 0
        self._state = "open"
        self._samples = 0
        self._last_ratio = 1.0

    def update(self, frame, det) -> None:
        import cv2
        import numpy as np

        row = det.row.flatten()
        rex, rey, lex, ley = row[4], row[5], row[6], row[7]
        eye_dist = math.hypot(lex - rex, ley - rey)
        if eye_dist < 8:
            return
        half = max(5, int(0.20 * eye_dist))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]

        energies = []
        for (ex, ey) in ((rex, rey), (lex, ley)):
            x0, y0 = int(ex) - half, int(ey) - half
            x1, y1 = int(ex) + half, int(ey) + half
            if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
                return  # eye near edge; skip this frame rather than guess
            patch = gray[y0:y1, x0:x1]
            if patch.size == 0:
                return
            patch = cv2.equalizeHist(patch)  # reduce lighting dependence
            energies.append(float(cv2.Laplacian(patch, cv2.CV_64F).var()))

        openness = sum(energies) / len(energies)
        self._samples += 1
        if self._samples <= self.WARMUP:
            self.baseline = max(self.baseline, openness)
            return
        if self.baseline <= 0:
            self.baseline = openness or 1.0

        ratio = openness / self.baseline if self.baseline else 1.0
        self._last_ratio = ratio
        if self._state == "open":
            if ratio < self.CLOSE_RATIO:
                self._state = "closed"
            else:
                self.baseline = max(self.baseline, openness)  # track open level
        else:  # closed
            if ratio > self.OPEN_RATIO:
                self._state = "open"
                self.blinks += 1

    def progress(self) -> float:
        if self.blinks >= 1:
            return 1.0
        # partial credit as the eye closes, so the UI bar moves during a blink
        return max(0.15, min(0.9, 1.0 - self._last_ratio))


class LivenessTracker:
    TURN_RANGE = 0.22
    NOD_RANGE = 0.18
    MOTION_MIN = 0.0015

    def __init__(self, challenge: str = "blink", min_sharpness: float = 45.0) -> None:
        self.challenge = challenge
        self.min_sharpness = float(min_sharpness)
        self._yaw: list[float] = []
        self._pitch: list[float] = []
        self._sharpness_best = 0.0
        self._samples = 0
        self._blink = _BlinkDetector()

    def update(self, det, aligned, frame=None) -> None:
        import numpy as np
        import cv2

        row = det.row.flatten()
        rex, rey, lex, ley = row[4], row[5], row[6], row[7]
        nx, ny = row[8], row[9]
        eye_mid_x = (rex + lex) / 2.0
        eye_mid_y = (rey + ley) / 2.0
        eye_dist = math.hypot(lex - rex, ley - rey) or 1.0

        self._yaw.append((nx - eye_mid_x) / eye_dist)
        self._pitch.append((ny - eye_mid_y) / eye_dist)

        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        self._sharpness_best = max(
            self._sharpness_best, float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        self._samples += 1

        if self.challenge == "blink" and frame is not None:
            self._blink.update(frame, det)

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
        if self.challenge == "blink":
            return self._blink.progress()
        if self.challenge == "nod":
            return min(1.0, self._rng(self._pitch) / self.NOD_RANGE)
        if self.challenge == "motion":
            return min(1.0, self._var(self._yaw) / self.MOTION_MIN)
        return min(1.0, self._rng(self._yaw) / self.TURN_RANGE)

    def passed(self) -> tuple[bool, str]:
        """Return (ok, reason_code). Codes are localised by the GUI."""
        if self._samples < 5:
            return False, "need_frames"
        if self._sharpness_best < self.min_sharpness:
            return False, "flat_image"
        if self.challenge == "blink":
            if self._blink.blinks >= 1:
                return True, "live_ok"
            return False, "do_challenge"
        if self._var(self._yaw) < self.MOTION_MIN and self.challenge != "nod":
            return False, "no_motion"
        if self.progress() < 1.0:
            return False, "do_challenge"
        return True, "live_ok"
