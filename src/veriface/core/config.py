"""Non-secret user settings, persisted as plain JSON.

Secrets (face templates, vault entries) are NOT stored here - they live in
separate DPAPI-encrypted files (see store.py).
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field, asdict
from typing import Any

from . import paths


@dataclass
class Config:
    # --- language ---------------------------------------------------------
    language: str = "ko"               # ko | en  (UI language)

    # --- recognition model / profile -------------------------------------
    profile: str = "balanced"          # lite | balanced | accurate (set by PC Analysis)
    det_size: int = 320                # YuNet detector input (square)
    match_threshold: float = 0.363     # SFace cosine threshold (OpenCV default)
    camera_index: int = 0
    keep_model_loaded: bool = False    # False => free model+camera after each session

    # --- enrollment -------------------------------------------------------
    enroll_samples: int = 12           # varied captures (glasses on/off, angles...)

    # --- liveness / anti-spoofing ----------------------------------------
    liveness_enabled: bool = True
    liveness_challenge: str = "blink"  # blink | turn | nod | motion
    min_face_sharpness: float = 45.0   # Laplacian variance floor (rejects flat photos)

    # --- adaptive templates (appearance changes over time / aging) -------
    adaptive_update: bool = True       # learn gradual appearance changes
    adaptive_min_score: float = 0.5    # only learn from very confident matches
    max_templates: int = 40            # cap; oldest embeddings are evicted first

    # --- scope: which features are active --------------------------------
    enable_vault: bool = True
    enable_session_guard: bool = False  # app-level auto-lock of the vault
    vault_autolock_seconds: int = 180

    # --- behaviour --------------------------------------------------------
    auth_timeout_seconds: int = 10      # give up a single auth attempt after N s
    hardware_report: dict = field(default_factory=dict)  # cached last PC Analysis

    # ---------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        paths.ensure_dirs()
        if paths.CONFIG_PATH.exists():
            try:
                raw = json.loads(paths.CONFIG_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raw = {}
            known = {f.name for f in dataclasses.fields(cls)}
            return cls(**{k: v for k, v in raw.items() if k in known})
        cfg = cls()
        cfg.save()
        return cfg

    def save(self) -> None:
        paths.ensure_dirs()
        tmp = paths.CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(paths.CONFIG_PATH)

    def apply(self, **changes: Any) -> None:
        for k, v in changes.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.save()
