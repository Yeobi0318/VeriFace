"""PC analysis: inspect the machine and recommend an optimal recognition profile.

Kept dependency-light (psutil only) and fast so the "PC Analysis" button is
instant. GPU detection is best-effort and purely informational: the pip build
of OpenCV runs on CPU, where YuNet + SFace are already real-time, so a GPU only
raises the recommended detector resolution rather than changing the backend.
"""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass, asdict, field


@dataclass
class HardwareReport:
    os: str = ""
    cpu: str = ""
    physical_cores: int = 0
    logical_cores: int = 0
    ram_gb: float = 0.0
    gpus: list[str] = field(default_factory=list)
    has_discrete_gpu: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _detect_gpus() -> list[str]:
    """Return a list of GPU names, best-effort, without hard dependencies."""
    names: list[str] = []
    # NVIDIA first - cheap and precise when present.
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode == 0:
            names += [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    if names:
        return names
    # Fall back to the display adapters Windows knows about.
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=8,
        )
        if out.returncode == 0:
            names += [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    return names


def _cpu_name() -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor).Name"],
            capture_output=True, text=True, timeout=8,
        )
        if out.returncode == 0 and out.stdout.strip():
            return " ".join(out.stdout.split())
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or "Unknown CPU"


def analyze() -> HardwareReport:
    import psutil  # local import keeps module import cheap

    gpus = _detect_gpus()
    discrete = any(
        kw in g.lower()
        for g in gpus
        for kw in ("nvidia", "geforce", "rtx", "gtx", "radeon rx", "arc")
    )
    return HardwareReport(
        os=f"{platform.system()} {platform.release()} ({platform.version()})",
        cpu=_cpu_name(),
        physical_cores=psutil.cpu_count(logical=False) or 0,
        logical_cores=psutil.cpu_count(logical=True) or 0,
        ram_gb=round(psutil.virtual_memory().total / (1024 ** 3), 1),
        gpus=gpus,
        has_discrete_gpu=discrete,
    )


@dataclass
class Recommendation:
    profile: str                 # lite | balanced | accurate
    det_size: int                # YuNet detector input (square px)
    enroll_samples: int
    liveness_enabled: bool
    rationale: str


def recommend(report: HardwareReport) -> Recommendation:
    """Map a hardware report to a recognition profile.

    Accuracy is the priority; the knobs we turn (detector resolution, number of
    enrolled samples) trade compute for accuracy, so stronger machines get the
    higher-accuracy settings while weak machines stay responsive.
    """
    score = report.logical_cores + report.ram_gb / 4.0
    if report.has_discrete_gpu:
        score += 6

    if score >= 16:
        return Recommendation(
            "accurate", 640, 16, True,
            "High-end hardware (discrete GPU and/or many cores): using the "
            "640px detector and 16 enrollment samples for maximum accuracy.",
        )
    if score >= 8:
        return Recommendation(
            "balanced", 320, 12, True,
            "Mainstream hardware: 320px detector with 12 samples - the best "
            "accuracy/latency balance for real-time CPU recognition.",
        )
    return Recommendation(
        "lite", 256, 8, True,
        "Lightweight hardware: 256px detector with 8 samples to keep "
        "recognition fast and memory use low.",
    )
