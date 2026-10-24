"""Command-line interface for VeriFace.

Running the exe with no arguments opens the GUI. Subcommands make the same
engine scriptable (e.g. so you can wire `veriface auth` into your own tooling):

    veriface               launch the GUI (default)
    veriface analyze       print PC analysis + chosen profile
    veriface install       download the recommended models (asks first)
    veriface enroll        enrol your face from the terminal
    veriface auth          verify your face; exit code 0 = match, 1 = no match
"""
from __future__ import annotations

import argparse
import sys
import threading

from .version import __version__, APP_NAME
from .core import hardware, model_manager
from .core.config import Config


def _cmd_analyze(_args) -> int:
    report = hardware.analyze()
    rec = hardware.recommend(report)
    Config.load().apply(profile=rec.profile, det_size=rec.det_size,
                        enroll_samples=rec.enroll_samples,
                        liveness_enabled=rec.liveness_enabled,
                        hardware_report=report.as_dict())
    print(f"OS    : {report.os}")
    print(f"CPU   : {report.cpu} ({report.logical_cores} threads)")
    print(f"RAM   : {report.ram_gb} GB")
    print(f"GPU   : {', '.join(report.gpus) or 'none detected'}")
    print(f"\nRecommended profile: {rec.profile}")
    print(f"  models : YuNet + SFace (OpenCV Zoo)")
    print(f"  tuning : detector {rec.det_size}px, {rec.enroll_samples} samples")
    print(f"  why    : {rec.rationale}")
    print(f"\nModels installed: {'yes' if model_manager.all_installed() else 'no'}")
    return 0


def _cmd_install(_args) -> int:
    if model_manager.all_installed():
        print("Models already installed.")
        return 0
    specs = model_manager.missing()
    print("The following open-source models will be downloaded:")
    for s in specs:
        print(f"  - {s.filename}  [{s.role}]")
    if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Cancelled.")
        return 1

    def progress(name, done, total):
        pct = (done / total * 100) if total else 0
        sys.stdout.write(f"\r  {name}: {pct:5.1f}%")
        sys.stdout.flush()
    model_manager.ensure_installed(progress)
    print("\nDone.")
    return 0


def _cmd_enroll(_args) -> int:
    from .core.enrollment import EnrollmentSession
    from .core.store import TemplateStore
    if not model_manager.all_installed():
        print("Models not installed. Run `veriface install` first.")
        return 1
    cfg = Config.load()
    done = threading.Event()

    def on_update(_frame, info):
        sys.stdout.write(f"\r  samples {info.get('count',0)}/{info.get('target',0)} "
                         f"- {info.get('status','')[:48]:48}")
        sys.stdout.flush()

    session = EnrollmentSession(cfg, on_update)
    print("Look at the camera; slowly change your angle (glasses on/off helps).")
    session.start(lambda res: done.set())
    done.wait()
    if len(session.embeddings) >= 3:
        TemplateStore().save(session.embeddings, {"profile": cfg.profile})
        print(f"\nEnrolled {len(session.embeddings)} samples.")
        return 0
    print("\nEnrollment failed - not enough samples.")
    return 1


def _cmd_auth(args) -> int:
    from .core.authenticator import verify_blocking
    res = verify_blocking(Config.load(), timeout=args.timeout)
    print(f"{'MATCH' if res.ok else 'NO MATCH'}  score={res.score:.3f}  ({res.message})")
    return 0 if res.ok else 1


def _cmd_gui(_args) -> int:
    from .app import main
    main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="veriface", description=f"{APP_NAME} {__version__}")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("analyze", help="analyze this PC and pick a model profile")
    sub.add_parser("install", help="download the recommended models")
    sub.add_parser("enroll", help="enrol your face from the terminal")
    a = sub.add_parser("auth", help="verify your face (exit 0 = match)")
    a.add_argument("--timeout", type=int, default=10)
    sub.add_parser("gui", help="launch the graphical app (default)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "analyze": _cmd_analyze, "install": _cmd_install, "enroll": _cmd_enroll,
        "auth": _cmd_auth, "gui": _cmd_gui, None: _cmd_gui,
    }[args.cmd]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
