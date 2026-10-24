"""VeriFace desktop GUI (CustomTkinter).

Design goals reflected here:
* Instant start - no heavy AI import at launch; models load only during a
  session, and the preview pump stops the moment a session ends.
* User-friendly - one window, clearly labelled tabs, plain-language status.
* Honest - the About tab states exactly what VeriFace does and does not secure.
"""
from __future__ import annotations

import threading
import time
import webbrowser
from typing import Callable, Optional

import customtkinter as ctk

from .version import __version__, APP_NAME
from .core import hardware, model_manager, win_hello
from .core.config import Config
from .core.store import TemplateStore, VaultStore
from .core.enrollment import EnrollmentSession, EnrollResult
from .core.authenticator import AuthSession, AuthResult

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

PREVIEW_W, PREVIEW_H = 480, 360


def _bgr_to_image(frame, bbox=None, max_w: int = PREVIEW_W):
    """Convert a BGR frame to a CTkImage, optionally drawing a face box."""
    import cv2
    from PIL import Image

    f = frame
    if bbox is not None:
        x, y, w, h = bbox
        f = frame.copy()
        cv2.rectangle(f, (x, y), (x + w, y + h), (0, 200, 0), 2)
    h0, w0 = f.shape[:2]
    scale = min(max_w / w0, PREVIEW_H / h0, 1.0)
    f = cv2.resize(f, (int(w0 * scale), int(h0 * scale)))
    rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=(pil.width, pil.height))


class VeriFaceApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("760x620")
        self.minsize(720, 580)

        # session / preview state (shared between worker thread and UI thread)
        self._preview_lock = threading.Lock()
        self._latest: Optional[tuple] = None
        self._session = None
        self._session_done = False
        self._session_result = None
        self._on_complete: Optional[Callable] = None
        self._pumping = False
        self._vault_relock_at = 0.0

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)
        for name in ("Status", "PC Analysis", "Enroll", "Vault",
                     "Login & Chrome", "Settings", "About"):
            self.tabs.add(name)
        self._build_status()
        self._build_analysis()
        self._build_enroll()
        self._build_vault()
        self._build_login_chrome()
        self._build_settings()
        self._build_about()
        self._refresh_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================ util
    def _toast(self, text: str) -> None:
        self.status_line.configure(text=text)

    def _start_pump(self) -> None:
        if not self._pumping:
            self._pumping = True
            self._pump()

    def _pump(self) -> None:
        if not self._pumping:
            return
        with self._preview_lock:
            latest = self._latest
        if latest is not None:
            frame, info = latest
            try:
                img = _bgr_to_image(frame, info.get("bbox"))
                self.preview.configure(image=img, text="")
                self.preview._img_ref = img  # prevent GC
            except Exception:
                pass
            self._session_status.configure(text=info.get("status", ""))
            if "count" in info and "target" in info:
                self.enroll_bar.set(info["count"] / max(1, info["target"]))
        if self._session_done:
            self._pumping = False
            self._finish_session()
            return
        self.after(33, self._pump)

    def _run_session(self, session, on_complete: Callable) -> None:
        self._session = session
        self._session_done = False
        self._session_result = None
        self._on_complete = on_complete
        self._latest = None

        def on_update(frame, info):
            with self._preview_lock:
                self._latest = (frame, info)

        def on_done(result):
            self._session_result = result
            self._session_done = True

        session.on_update = on_update
        session.start(on_done)
        self._start_pump()

    def _finish_session(self) -> None:
        result = self._session_result
        self._session = None
        cb, self._on_complete = self._on_complete, None
        if cb:
            cb(result)

    def _stop_session(self) -> None:
        if self._session is not None:
            self._session.stop()

    # ============================================================== STATUS
    def _build_status(self) -> None:
        t = self.tabs.tab("Status")
        ctk.CTkLabel(t, text=f"{APP_NAME}", font=("", 26, "bold")).pack(pady=(14, 0))
        ctk.CTkLabel(t, text="Local face authentication for your own machine",
                     text_color="gray").pack()

        self.status_card = ctk.CTkLabel(t, text="", justify="left", font=("", 14))
        self.status_card.pack(pady=16, padx=16, anchor="w")

        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=6)
        self.btn_test = ctk.CTkButton(row, text="🔓  Test face unlock",
                                      command=self._test_unlock, width=200, height=40)
        self.btn_test.grid(row=0, column=0, padx=6)
        ctk.CTkButton(row, text="🔒  Lock Windows now", width=200, height=40,
                      fg_color="gray30", command=self._lock_windows).grid(
            row=0, column=1, padx=6)

        self.status_line = ctk.CTkLabel(t, text="", text_color="gray")
        self.status_line.pack(pady=(10, 0))

    def _refresh_status(self) -> None:
        ts = TemplateStore()
        enrolled = (f"Enrolled  ({len(ts.embeddings())} samples)"
                    if ts.enrolled else "Not enrolled")
        models = "Installed" if model_manager.all_installed() else "Not installed"
        self.status_card.configure(text=(
            f"Face template :  {enrolled}\n"
            f"AI models      :  {models}\n"
            f"Profile        :  {self.cfg.profile}  "
            f"(detector {self.cfg.det_size}px, threshold {self.cfg.match_threshold})\n"
            f"Liveness       :  {'on' if self.cfg.liveness_enabled else 'off'} "
            f"({self.cfg.liveness_challenge})\n"
            f"Vault          :  {'enabled' if self.cfg.enable_vault else 'disabled'}"
        ))
        self.btn_test.configure(
            state="normal" if (ts.enrolled and model_manager.all_installed())
            else "disabled")

    def _lock_windows(self) -> None:
        import ctypes
        ctypes.windll.user32.LockWorkStation()

    def _test_unlock(self) -> None:
        self.tabs.set("Status")
        self.btn_test.configure(state="disabled")
        self._toast("Starting camera...")

        def done(res: AuthResult):
            self.btn_test.configure(state="normal")
            self._toast(f"{'✅' if res.ok else '❌'}  {res.message} "
                        f"(score {res.score:.3f})")
        self._run_session(AuthSession(self.cfg, lambda *_: None), done)

    # ============================================================ ANALYSIS
    def _build_analysis(self) -> None:
        t = self.tabs.tab("PC Analysis")
        ctk.CTkLabel(t, text="Analyze this PC and pick the best local model",
                     font=("", 16, "bold")).pack(pady=(14, 4))
        ctk.CTkButton(t, text="🔍  PC Analysis", width=200, height=42,
                      command=self._do_analysis).pack(pady=8)
        self.analysis_box = ctk.CTkTextbox(t, height=230, width=680)
        self.analysis_box.pack(pady=8, padx=12)
        self.analysis_box.configure(state="disabled")
        self.install_bar = ctk.CTkProgressBar(t, width=680)
        self.install_bar.set(0)
        self.install_bar.pack(pady=(4, 2), padx=12)
        self.btn_install = ctk.CTkButton(t, text="⬇  Install recommended models",
                                         command=self._install_models, state="disabled")
        self.btn_install.pack(pady=6)

    def _set_analysis_text(self, text: str) -> None:
        self.analysis_box.configure(state="normal")
        self.analysis_box.delete("1.0", "end")
        self.analysis_box.insert("1.0", text)
        self.analysis_box.configure(state="disabled")

    def _do_analysis(self) -> None:
        self._set_analysis_text("Analyzing hardware...")

        def work():
            report = hardware.analyze()
            rec = hardware.recommend(report)
            self._latest_report = report
            self._latest_rec = rec
            self.after(0, lambda: self._show_analysis(report, rec))
        threading.Thread(target=work, daemon=True).start()

    def _show_analysis(self, report, rec) -> None:
        # Persist the chosen profile immediately so recognition uses it.
        self.cfg.apply(profile=rec.profile, det_size=rec.det_size,
                       enroll_samples=rec.enroll_samples,
                       liveness_enabled=rec.liveness_enabled,
                       hardware_report=report.as_dict())
        installed = model_manager.all_installed()
        lines = [
            "── Hardware ─────────────────────────────",
            f"OS    : {report.os}",
            f"CPU   : {report.cpu}",
            f"Cores : {report.physical_cores} physical / {report.logical_cores} logical",
            f"RAM   : {report.ram_gb} GB",
            f"GPU   : {', '.join(report.gpus) or 'none detected'}",
            "",
            "── Recommended profile ─────────────────",
            f"Profile : {rec.profile}",
            f"Models  : YuNet (detection) + SFace (recognition)  [OpenCV Zoo, Apache-2.0]",
            f"Tuning  : detector {rec.det_size}px, {rec.enroll_samples} enroll samples, "
            f"liveness {'on' if rec.liveness_enabled else 'off'}",
            f"Why     : {rec.rationale}",
            "",
            f"Models installed : {'yes' if installed else 'NO - click Install below'}",
        ]
        self._set_analysis_text("\n".join(lines))
        self.btn_install.configure(state="disabled" if installed else "normal")
        self._refresh_status()

    def _install_models(self) -> None:
        self.btn_install.configure(state="disabled")
        self.install_bar.set(0)

        def progress(name, done, total):
            frac = (done / total) if total else 0
            self.after(0, lambda: self.install_bar.set(frac))

        def work():
            try:
                fetched = model_manager.ensure_installed(progress)
                msg = ("Already installed." if not fetched
                       else "Installed: " + ", ".join(fetched))
            except Exception as exc:
                msg = f"Install failed: {exc}"
            self.after(0, lambda: self._after_install(msg))
        threading.Thread(target=work, daemon=True).start()

    def _after_install(self, msg: str) -> None:
        self.install_bar.set(1.0 if model_manager.all_installed() else 0)
        box = self.analysis_box
        box.configure(state="normal")
        box.insert("end", f"\n{msg}\n")
        box.configure(state="disabled")
        self._refresh_status()

    # ============================================================== ENROLL
    def _build_enroll(self) -> None:
        t = self.tabs.tab("Enroll")
        ctk.CTkLabel(t, text="Enroll your face",
                     font=("", 16, "bold")).pack(pady=(12, 0))
        ctk.CTkLabel(
            t, text="Tip: slowly change angle and enrol BOTH with and without "
                    "glasses for best accuracy.", text_color="gray").pack()
        self.preview = ctk.CTkLabel(t, text="(camera preview)", width=PREVIEW_W,
                                    height=PREVIEW_H, fg_color="gray20")
        self.preview.pack(pady=10)
        self._session_status = ctk.CTkLabel(t, text="", text_color="gray")
        self._session_status.pack()
        self.enroll_bar = ctk.CTkProgressBar(t, width=PREVIEW_W)
        self.enroll_bar.set(0)
        self.enroll_bar.pack(pady=6)
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=6)
        self.btn_enroll = ctk.CTkButton(row, text="▶  Start enrollment",
                                        command=self._start_enroll, width=180)
        self.btn_enroll.grid(row=0, column=0, padx=6)
        ctk.CTkButton(row, text="■  Cancel", fg_color="gray30", width=120,
                      command=self._stop_session).grid(row=0, column=1, padx=6)
        ctk.CTkButton(row, text="🗑  Delete template", fg_color="#8a2d2d", width=150,
                      command=self._delete_template).grid(row=0, column=2, padx=6)

    def _start_enroll(self) -> None:
        if not model_manager.all_installed():
            self._session_status.configure(
                text="Models not installed - run PC Analysis first.")
            return
        self.tabs.set("Enroll")
        self.btn_enroll.configure(state="disabled")
        self.enroll_bar.set(0)

        def done(res: EnrollResult):
            self.btn_enroll.configure(state="normal")
            embeddings = getattr(self._enroll_ref, "embeddings", [])
            if len(embeddings) >= 3:
                TemplateStore().save(embeddings, {"profile": self.cfg.profile})
                self._session_status.configure(
                    text=f"✅ Saved {len(embeddings)} samples. {res.message}")
            else:
                self._session_status.configure(
                    text=f"❌ Not enough samples captured. {res.message}")
            self._refresh_status()

        session = EnrollmentSession(self.cfg, lambda *_: None)
        self._enroll_ref = session
        self._run_session(session, done)

    def _delete_template(self) -> None:
        TemplateStore().clear()
        self._session_status.configure(text="Template deleted.")
        self._refresh_status()

    # =============================================================== VAULT
    def _build_vault(self) -> None:
        t = self.tabs.tab("Vault")
        self.vault_locked_frame = ctk.CTkFrame(t, fg_color="transparent")
        self.vault_unlocked_frame = ctk.CTkFrame(t, fg_color="transparent")

        ctk.CTkLabel(self.vault_locked_frame, text="🔒  Vault is locked",
                     font=("", 20, "bold")).pack(pady=(60, 8))
        ctk.CTkLabel(self.vault_locked_frame,
                     text="Unlock with your face to view saved passwords.",
                     text_color="gray").pack()
        ctk.CTkButton(self.vault_locked_frame, text="🔓  Unlock with face",
                      width=200, height=42, command=self._unlock_vault).pack(pady=16)
        self.vault_lock_msg = ctk.CTkLabel(self.vault_locked_frame, text="",
                                           text_color="gray")
        self.vault_lock_msg.pack()

        top = ctk.CTkFrame(self.vault_unlocked_frame, fg_color="transparent")
        top.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(top, text="🔓 Vault unlocked", font=("", 14, "bold")).pack(side="left")
        ctk.CTkButton(top, text="Lock", width=70, fg_color="gray30",
                      command=self._lock_vault).pack(side="right")
        ctk.CTkButton(top, text="+ Add", width=70,
                      command=self._add_entry_dialog).pack(side="right", padx=6)
        self.vault_list = ctk.CTkScrollableFrame(self.vault_unlocked_frame, height=380)
        self.vault_list.pack(fill="both", expand=True)

        self.vault_locked_frame.pack(fill="both", expand=True)

    def _unlock_vault(self) -> None:
        if not self.cfg.enable_vault:
            self.vault_lock_msg.configure(text="Vault is disabled in Settings.")
            return
        if not (TemplateStore().enrolled and model_manager.all_installed()):
            self.vault_lock_msg.configure(text="Enroll your face and install models first.")
            return
        self.vault_lock_msg.configure(text="Starting camera...")

        def done(res: AuthResult):
            if res.ok:
                self._show_vault_unlocked()
            else:
                self.vault_lock_msg.configure(text=f"❌ {res.message} (score {res.score:.3f})")
        self._run_session(AuthSession(self.cfg, lambda *_: None), done)

    def _show_vault_unlocked(self) -> None:
        self.vault_locked_frame.pack_forget()
        self.vault_unlocked_frame.pack(fill="both", expand=True)
        self._refresh_vault_list()
        self._vault_relock_at = time.time() + max(30, self.cfg.vault_autolock_seconds)
        self._schedule_relock()

    def _schedule_relock(self) -> None:
        if not self.vault_unlocked_frame.winfo_ismapped():
            return
        if time.time() >= self._vault_relock_at:
            self._lock_vault()
            return
        self.after(1000, self._schedule_relock)

    def _lock_vault(self) -> None:
        self.vault_unlocked_frame.pack_forget()
        self.vault_locked_frame.pack(fill="both", expand=True)
        self.vault_lock_msg.configure(text="Locked.")

    def _refresh_vault_list(self) -> None:
        for w in self.vault_list.winfo_children():
            w.destroy()
        entries = VaultStore().entries()
        if not entries:
            ctk.CTkLabel(self.vault_list, text="No saved passwords yet. Click + Add.",
                         text_color="gray").pack(pady=20)
            return
        for e in entries:
            card = ctk.CTkFrame(self.vault_list)
            card.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(card, text=f"{e.get('title','')}  ·  {e.get('username','')}",
                         font=("", 13, "bold")).pack(side="left", padx=8, pady=8)
            ctk.CTkButton(card, text="Copy", width=60,
                          command=lambda s=e.get("secret", ""): self._copy_secret(s)
                          ).pack(side="right", padx=6)
            ctk.CTkButton(card, text="Delete", width=70, fg_color="#8a2d2d",
                          command=lambda i=e.get("id"): self._delete_entry(i)
                          ).pack(side="right")
            self._bump_relock()

    def _copy_secret(self, secret: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(secret)
        self._bump_relock()
        self.after(20000, self.clipboard_clear)  # auto-wipe clipboard after 20s

    def _delete_entry(self, entry_id: str) -> None:
        VaultStore().delete(entry_id)
        self._refresh_vault_list()

    def _bump_relock(self) -> None:
        self._vault_relock_at = time.time() + max(30, self.cfg.vault_autolock_seconds)

    def _add_entry_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Add entry")
        dlg.geometry("360x320")
        dlg.transient(self)
        fields = {}
        for label in ("Title", "Username", "URL"):
            ctk.CTkLabel(dlg, text=label).pack(anchor="w", padx=16, pady=(10, 0))
            ent = ctk.CTkEntry(dlg, width=320)
            ent.pack(padx=16)
            fields[label] = ent
        ctk.CTkLabel(dlg, text="Password / secret").pack(anchor="w", padx=16, pady=(10, 0))
        secret = ctk.CTkEntry(dlg, width=320, show="•")
        secret.pack(padx=16)

        def save():
            VaultStore().add(fields["Title"].get(), fields["Username"].get(),
                             secret.get(), fields["URL"].get())
            dlg.destroy()
            self._refresh_vault_list()
        ctk.CTkButton(dlg, text="Save", command=save).pack(pady=16)

    # ====================================================== LOGIN & CHROME
    def _build_login_chrome(self) -> None:
        t = self.tabs.tab("Login & Chrome")
        ctk.CTkLabel(t, text="Face login for Windows & Chrome",
                     font=("", 16, "bold")).pack(pady=(12, 2))
        ctk.CTkLabel(
            t, justify="left", text_color="gray",
            text="The secure, supported way to use your face instead of the PIN "
                 "for\nthe Windows sign-in AND Chrome passwords is Windows Hello "
                 "Face.").pack(pady=(0, 8))

        steps = ctk.CTkTextbox(t, height=190, width=690)
        steps.pack(padx=12)
        steps.insert("1.0", LOGIN_STEPS)
        steps.configure(state="disabled")

        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkButton(row, text="🔍  Check this PC", width=150,
                      command=self._check_hello).grid(row=0, column=0, padx=5)
        ctk.CTkButton(row, text="⚙  Windows sign-in settings", width=210,
                      command=win_hello.open_signin_settings).grid(row=0, column=1, padx=5)
        ctk.CTkButton(row, text="🌐  Chrome passwords", width=170, fg_color="gray30",
                      command=win_hello.open_chrome_password_settings).grid(
            row=0, column=2, padx=5)

        self.hello_result = ctk.CTkLabel(t, text="", justify="left", wraplength=680)
        self.hello_result.pack(pady=(4, 2), padx=12, anchor="w")

    def _check_hello(self) -> None:
        self.hello_result.configure(text="Checking cameras and Hello capability...")

        def work():
            st = win_hello.detect()
            cams = ", ".join(st.cameras) or "none"
            txt = (f"Cameras: {cams}\n"
                   f"IR camera (Hello Face): {'yes - ' + ', '.join(st.ir_cameras) if st.ir_cameras else 'not detected'}\n"
                   f"\n{st.note}")
            self.after(0, lambda: self.hello_result.configure(text=txt))
        threading.Thread(target=work, daemon=True).start()

    # ============================================================ SETTINGS
    def _build_settings(self) -> None:
        t = self.tabs.tab("Settings")
        wrap = ctk.CTkScrollableFrame(t, height=480)
        wrap.pack(fill="both", expand=True)

        self._sw_liveness = self._switch(wrap, "Liveness / anti-spoofing",
                                         self.cfg.liveness_enabled)
        self._sw_vault = self._switch(wrap, "Enable password vault",
                                      self.cfg.enable_vault)
        self._sw_keep = self._switch(wrap, "Keep model in memory between uses "
                                           "(faster, uses more RAM)",
                                     self.cfg.keep_model_loaded)

        self._slider(wrap, "Match threshold (higher = stricter)",
                     0.20, 0.60, self.cfg.match_threshold, "thr_val")
        self._slider(wrap, "Vault auto-lock (seconds)",
                     30, 600, self.cfg.vault_autolock_seconds, "lock_val", integer=True)

        ctk.CTkLabel(wrap, text="Liveness challenge").pack(anchor="w", padx=12, pady=(10, 0))
        self._challenge = ctk.CTkOptionMenu(wrap, values=["turn", "nod", "motion"])
        self._challenge.set(self.cfg.liveness_challenge)
        self._challenge.pack(anchor="w", padx=12)

        ctk.CTkLabel(wrap, text="Camera index").pack(anchor="w", padx=12, pady=(10, 0))
        self._cam_idx = ctk.CTkEntry(wrap, width=80)
        self._cam_idx.insert(0, str(self.cfg.camera_index))
        self._cam_idx.pack(anchor="w", padx=12)

        ctk.CTkButton(wrap, text="💾  Save settings", command=self._save_settings,
                      width=200, height=40).pack(pady=18)
        self.settings_msg = ctk.CTkLabel(wrap, text="", text_color="gray")
        self.settings_msg.pack()

    def _switch(self, parent, text, value):
        var = ctk.BooleanVar(value=value)
        ctk.CTkSwitch(parent, text=text, variable=var).pack(anchor="w", padx=12, pady=8)
        return var

    def _slider(self, parent, text, lo, hi, value, attr, integer=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        lbl = ctk.CTkLabel(row, text=f"{text}: {value}")
        lbl.pack(anchor="w")
        s = ctk.CTkSlider(row, from_=lo, to=hi)
        s.set(value)
        s.pack(fill="x")
        def upd(v):
            lbl.configure(text=f"{text}: {int(v) if integer else round(v, 3)}")
        s.configure(command=upd)
        setattr(self, attr, s)

    def _save_settings(self) -> None:
        try:
            cam = int(self._cam_idx.get())
        except ValueError:
            cam = 0
        self.cfg.apply(
            liveness_enabled=bool(self._sw_liveness.get()),
            enable_vault=bool(self._sw_vault.get()),
            keep_model_loaded=bool(self._sw_keep.get()),
            match_threshold=round(float(self.thr_val.get()), 3),
            vault_autolock_seconds=int(self.lock_val.get()),
            liveness_challenge=self._challenge.get(),
            camera_index=cam,
        )
        self.settings_msg.configure(text="Saved.")
        self._refresh_status()

    # =============================================================== ABOUT
    def _build_about(self) -> None:
        t = self.tabs.tab("About")
        box = ctk.CTkTextbox(t, width=700, height=480)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", ABOUT_TEXT.format(ver=__version__))
        box.configure(state="disabled")
        ctk.CTkButton(t, text="Project page", command=lambda: webbrowser.open(
            "https://github.com/Yeobi0318/VeriFace")).pack(pady=6)

    # =============================================================== close
    def _on_close(self) -> None:
        self._pumping = False
        self._stop_session()
        self.destroy()


ABOUT_TEXT = """VeriFace {ver}  -  local face authentication (research / educational)

WHAT IT DOES
  - Recognises YOU with open-source local AI (YuNet + SFace, OpenCV Zoo).
  - Everything runs offline; no image or embedding ever leaves this PC.
  - Face templates and the password vault are encrypted at rest with the
    Windows DPAPI, bound to your Windows user account.
  - The camera and AI model load only during a session and are released right
    after, so VeriFace uses ~no CPU/RAM while idle.

HONEST SECURITY NOTES  (please read)
  - This is a convenience + research tool, not a certified security product.
  - Liveness here is a BASIC active challenge (head turn/nod + texture check).
    It stops casual photo attacks but not a determined video-replay attacker.
  - VeriFace does NOT replace the Windows logon screen, and does NOT hook or
    read Chrome. For face login at the OS sign-in AND for Chrome's password
    prompt, use Windows Hello Face - see the "Login & Chrome" tab. That is the
    supported path; a custom credential provider would risk locking you out.
    VeriFace deliberately does not store or replay your Windows PIN.
  - The vault is a safe alternative to exporting browser passwords; VeriFace
    does NOT read or decrypt Chrome's password store.
  - Biometrics cannot be changed if leaked. Keep a Windows password/PIN as the
    real fallback.
"""


LOGIN_STEPS = """How to use your FACE instead of your PIN — the supported, secure way:

WINDOWS SIGN-IN (lock screen)
  1. Click "Windows sign-in settings" below (Settings > Accounts > Sign-in options).
  2. Open "Facial recognition (Windows Hello)" > Set up, and follow the wizard.
  3. From then on the lock screen recognises your face instead of asking the PIN.
     (Windows keeps your PIN as a recovery fallback — this is intentional.)

CHROME PASSWORDS
  1. Set up Windows Hello Face (above) first.
  2. Click "Chrome passwords" below, open Settings, and turn ON
     "Use Windows Hello when filling passwords".
  3. Chrome will now verify you by face before revealing/filling a password.

NOTE: Windows Hello Face needs an IR camera. Use "Check this PC" to see whether
yours has one. If it doesn't, OS/Chrome face login isn't available on this
device — but VeriFace's own in-app face unlock and vault still work.
"""


def main() -> None:
    app = VeriFaceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
