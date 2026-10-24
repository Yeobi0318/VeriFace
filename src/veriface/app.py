"""VeriFace desktop GUI (CustomTkinter), bilingual (Korean / English).

Design goals reflected here:
* Instant start - no heavy AI import at launch; models load only during a
  session, and the preview pump stops the moment a session ends.
* User-friendly - one window, clearly labelled tabs, plain-language status,
  switchable UI language.
* Honest - the About and "Login & Chrome" tabs state exactly what VeriFace
  does and does not secure.
"""
from __future__ import annotations

import threading
import time
import webbrowser
from typing import Callable, Optional

import customtkinter as ctk

from .version import __version__, APP_NAME
from .core import hardware, model_manager, win_hello, i18n
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
        self.lang = self.cfg.language if self.cfg.language in i18n.LANGUAGES else "ko"
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("780x660")
        self.minsize(740, 600)

        # session / preview state (shared between worker thread and UI thread)
        self._preview_lock = threading.Lock()
        self._latest: Optional[tuple] = None
        self._session = None
        self._session_done = False
        self._session_result = None
        self._on_complete: Optional[Callable] = None
        self._pumping = False
        self._vault_relock_at = 0.0

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- i18n
    def t(self, key: str, **kw) -> str:
        return i18n.t(key, self.lang, **kw)

    def _res_msg(self, code: str) -> str:
        known = {"complete", "cancelled", "no_enroll", "timeout", "recognized"}
        return self.t("res." + code) if code in known else code

    # ------------------------------------------------------------- build
    def _build_ui(self) -> None:
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)
        self._tabname = {k: self.t(f"tab.{k}") for k in
                         ("status", "analysis", "enroll", "vault",
                          "login", "settings", "about")}
        self._build_status(self.tabs.add(self._tabname["status"]))
        self._build_analysis(self.tabs.add(self._tabname["analysis"]))
        self._build_enroll(self.tabs.add(self._tabname["enroll"]))
        self._build_vault(self.tabs.add(self._tabname["vault"]))
        self._build_login_chrome(self.tabs.add(self._tabname["login"]))
        self._build_settings(self.tabs.add(self._tabname["settings"]))
        self._build_about(self.tabs.add(self._tabname["about"]))
        self._refresh_status()

    def _rebuild_ui(self) -> None:
        self._pumping = False
        self._stop_session()
        self.tabs.destroy()
        self.title(f"{APP_NAME} {__version__}")
        self._build_ui()

    # ================================================================ util
    def _toast(self, text: str) -> None:
        self.status_line.configure(text=text)

    def _start_pump(self) -> None:
        if not self._pumping:
            self._pumping = True
            self._pump()

    def _status_text(self, info: dict) -> str:
        sk = info.get("status_key")
        if not sk:
            return ""
        challenge = info.get("challenge", self.cfg.liveness_challenge)
        return self.t("st." + sk, hint=self.t("hint." + challenge))

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
            self._session_status.configure(text=self._status_text(info))
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
    def _build_status(self, t) -> None:
        ctk.CTkLabel(t, text=f"{APP_NAME}", font=("", 26, "bold")).pack(pady=(14, 0))
        ctk.CTkLabel(t, text=self.t("subtitle"), text_color="gray").pack()

        self.status_card = ctk.CTkLabel(t, text="", justify="left", font=("", 14))
        self.status_card.pack(pady=16, padx=16, anchor="w")

        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=6)
        self.btn_test = ctk.CTkButton(row, text=self.t("btn.test_unlock"),
                                      command=self._test_unlock, width=220, height=40)
        self.btn_test.grid(row=0, column=0, padx=6)
        ctk.CTkButton(row, text=self.t("btn.lock_windows"), width=200, height=40,
                      fg_color="gray30", command=self._lock_windows).grid(
            row=0, column=1, padx=6)

        self.status_line = ctk.CTkLabel(t, text="", text_color="gray")
        self.status_line.pack(pady=(10, 0))

    def _refresh_status(self) -> None:
        ts = TemplateStore()
        enrolled = (self.t("status.enrolled", n=ts.count())
                    if ts.enrolled else self.t("status.not_enrolled"))
        models = (self.t("status.installed") if model_manager.all_installed()
                  else self.t("status.not_installed"))
        live = (self.t("val.on") if self.cfg.liveness_enabled else self.t("val.off"))
        vault = (self.t("val.enabled") if self.cfg.enable_vault
                 else self.t("val.disabled"))
        challenge = self.t("challenge." + self.cfg.liveness_challenge)
        self.status_card.configure(text=(
            f"{self.t('status.template')} :  {enrolled}\n"
            f"{self.t('status.models')} :  {models}\n"
            f"{self.t('status.profile')} :  {self.cfg.profile}  "
            f"(det {self.cfg.det_size}px, thr {self.cfg.match_threshold})\n"
            f"{self.t('status.liveness')} :  {live} ({challenge})\n"
            f"{self.t('status.vault')} :  {vault}"
        ))
        self.btn_test.configure(
            state="normal" if (ts.enrolled and model_manager.all_installed())
            else "disabled")

    def _lock_windows(self) -> None:
        import ctypes
        ctypes.windll.user32.LockWorkStation()

    def _test_unlock(self) -> None:
        self.btn_test.configure(state="disabled")
        self._toast(self.t("status.starting_camera"))

        def done(res: AuthResult):
            self.btn_test.configure(state="normal")
            if res.ok:
                self._toast(self.t("status.unlock_ok", score=res.score))
            else:
                self._toast(self.t("status.unlock_fail",
                                   msg=self._res_msg(res.message), score=res.score))
        self._run_session(AuthSession(self.cfg, lambda *_: None), done)

    # ============================================================ ANALYSIS
    def _build_analysis(self, t) -> None:
        ctk.CTkLabel(t, text=self.t("analysis.title"),
                     font=("", 16, "bold")).pack(pady=(14, 4))
        ctk.CTkButton(t, text=self.t("btn.analyze"), width=200, height=42,
                      command=self._do_analysis).pack(pady=8)
        self.analysis_box = ctk.CTkTextbox(t, height=230, width=700)
        self.analysis_box.pack(pady=8, padx=12)
        self.analysis_box.configure(state="disabled")
        self.install_bar = ctk.CTkProgressBar(t, width=700)
        self.install_bar.set(0)
        self.install_bar.pack(pady=(4, 2), padx=12)
        self.btn_install = ctk.CTkButton(t, text=self.t("btn.install"),
                                         command=self._install_models, state="disabled")
        self.btn_install.pack(pady=6)

    def _set_analysis_text(self, text: str) -> None:
        self.analysis_box.configure(state="normal")
        self.analysis_box.delete("1.0", "end")
        self.analysis_box.insert("1.0", text)
        self.analysis_box.configure(state="disabled")

    def _do_analysis(self) -> None:
        self._set_analysis_text(self.t("analysis.analyzing"))

        def work():
            report = hardware.analyze()
            rec = hardware.recommend(report)
            self.after(0, lambda: self._show_analysis(report, rec))
        threading.Thread(target=work, daemon=True).start()

    def _show_analysis(self, report, rec) -> None:
        self.cfg.apply(profile=rec.profile, det_size=rec.det_size,
                       enroll_samples=rec.enroll_samples,
                       liveness_enabled=rec.liveness_enabled,
                       hardware_report=report.as_dict())
        installed = model_manager.all_installed()
        lines = [
            self.t("analysis.hardware"),
            f"OS    : {report.os}",
            f"CPU   : {report.cpu}",
            f"Cores : {report.physical_cores} / {report.logical_cores}",
            f"RAM   : {report.ram_gb} GB",
            f"GPU   : {', '.join(report.gpus) or self.t('login.none')}",
            "",
            self.t("analysis.recommended"),
            f"Profile : {rec.profile}",
            "Models  : YuNet + SFace  [OpenCV Zoo, Apache-2.0]",
            f"Tuning  : det {rec.det_size}px, {rec.enroll_samples} samples",
            f"Why     : {rec.rationale}",
            "",
            f"{self.t('analysis.models_installed')} : "
            f"{self.t('analysis.yes') if installed else self.t('analysis.no_install')}",
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
                msg = (self.t("install.already") if not fetched
                       else self.t("install.done", names=", ".join(fetched)))
            except Exception as exc:
                msg = self.t("install.failed", err=exc)
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
    def _build_enroll(self, t) -> None:
        ctk.CTkLabel(t, text=self.t("enroll.title"),
                     font=("", 16, "bold")).pack(pady=(12, 0))
        ctk.CTkLabel(t, text=self.t("enroll.tip"), text_color="gray").pack()
        self.preview = ctk.CTkLabel(t, text=self.t("enroll.preview"), width=PREVIEW_W,
                                    height=PREVIEW_H, fg_color="gray20")
        self.preview.pack(pady=10)
        self._session_status = ctk.CTkLabel(t, text="", text_color="gray")
        self._session_status.pack()
        self.enroll_bar = ctk.CTkProgressBar(t, width=PREVIEW_W)
        self.enroll_bar.set(0)
        self.enroll_bar.pack(pady=6)
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=6)
        self.btn_enroll = ctk.CTkButton(row, text=self.t("btn.start_enroll"),
                                        command=self._start_enroll, width=180)
        self.btn_enroll.grid(row=0, column=0, padx=6)
        ctk.CTkButton(row, text=self.t("btn.cancel"), fg_color="gray30", width=120,
                      command=self._stop_session).grid(row=0, column=1, padx=6)
        ctk.CTkButton(row, text=self.t("btn.delete_template"), fg_color="#8a2d2d",
                      width=150, command=self._delete_template).grid(
            row=0, column=2, padx=6)

    def _start_enroll(self) -> None:
        if not model_manager.all_installed():
            self._session_status.configure(text=self.t("enroll.models_missing"))
            return
        self.tabs.set(self._tabname["enroll"])
        self.btn_enroll.configure(state="disabled")
        self.enroll_bar.set(0)

        def done(res: EnrollResult):
            self.btn_enroll.configure(state="normal")
            embeddings = getattr(self._enroll_ref, "embeddings", [])
            if len(embeddings) >= 3:
                TemplateStore().save(embeddings, {"profile": self.cfg.profile})
                self._session_status.configure(text=self.t("enroll.saved",
                                                           n=len(embeddings)))
            else:
                self._session_status.configure(
                    text=self.t("enroll.not_enough", msg=self._res_msg(res.message)))
            self._refresh_status()

        session = EnrollmentSession(self.cfg, lambda *_: None)
        self._enroll_ref = session
        self._run_session(session, done)

    def _delete_template(self) -> None:
        TemplateStore().clear()
        self._session_status.configure(text=self.t("enroll.deleted"))
        self._refresh_status()

    # =============================================================== VAULT
    def _build_vault(self, t) -> None:
        self.vault_locked_frame = ctk.CTkFrame(t, fg_color="transparent")
        self.vault_unlocked_frame = ctk.CTkFrame(t, fg_color="transparent")

        ctk.CTkLabel(self.vault_locked_frame, text=self.t("vault.locked_title"),
                     font=("", 20, "bold")).pack(pady=(60, 8))
        ctk.CTkLabel(self.vault_locked_frame, text=self.t("vault.unlock_hint"),
                     text_color="gray").pack()
        ctk.CTkButton(self.vault_locked_frame, text=self.t("btn.unlock_face"),
                      width=200, height=42, command=self._unlock_vault).pack(pady=16)
        self.vault_lock_msg = ctk.CTkLabel(self.vault_locked_frame, text="",
                                           text_color="gray")
        self.vault_lock_msg.pack()

        top = ctk.CTkFrame(self.vault_unlocked_frame, fg_color="transparent")
        top.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(top, text=self.t("vault.unlocked_title"),
                     font=("", 14, "bold")).pack(side="left")
        ctk.CTkButton(top, text=self.t("btn.lock"), width=70, fg_color="gray30",
                      command=self._lock_vault).pack(side="right")
        ctk.CTkButton(top, text=self.t("btn.add"), width=80,
                      command=self._add_entry_dialog).pack(side="right", padx=6)
        self.vault_list = ctk.CTkScrollableFrame(self.vault_unlocked_frame, height=380)
        self.vault_list.pack(fill="both", expand=True)

        self.vault_locked_frame.pack(fill="both", expand=True)

    def _unlock_vault(self) -> None:
        if not self.cfg.enable_vault:
            self.vault_lock_msg.configure(text=self.t("vault.disabled"))
            return
        if not (TemplateStore().enrolled and model_manager.all_installed()):
            self.vault_lock_msg.configure(text=self.t("vault.enroll_first"))
            return
        self.vault_lock_msg.configure(text=self.t("status.starting_camera"))

        def done(res: AuthResult):
            if res.ok:
                self._show_vault_unlocked()
            else:
                self.vault_lock_msg.configure(
                    text=self.t("status.unlock_fail",
                                msg=self._res_msg(res.message), score=res.score))
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
        self.vault_lock_msg.configure(text=self.t("vault.locked"))

    def _refresh_vault_list(self) -> None:
        for w in self.vault_list.winfo_children():
            w.destroy()
        entries = VaultStore().entries()
        if not entries:
            ctk.CTkLabel(self.vault_list, text=self.t("vault.empty"),
                         text_color="gray").pack(pady=20)
            return
        for e in entries:
            card = ctk.CTkFrame(self.vault_list)
            card.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(card, text=f"{e.get('title','')}  ·  {e.get('username','')}",
                         font=("", 13, "bold")).pack(side="left", padx=8, pady=8)
            ctk.CTkButton(card, text=self.t("btn.copy"), width=60,
                          command=lambda s=e.get("secret", ""): self._copy_secret(s)
                          ).pack(side="right", padx=6)
            ctk.CTkButton(card, text=self.t("btn.delete"), width=70, fg_color="#8a2d2d",
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
        dlg.title(self.t("dialog.add_title"))
        dlg.geometry("360x340")
        dlg.transient(self)
        fields = {}
        for key in ("field.title", "field.username", "field.url"):
            ctk.CTkLabel(dlg, text=self.t(key)).pack(anchor="w", padx=16, pady=(10, 0))
            ent = ctk.CTkEntry(dlg, width=320)
            ent.pack(padx=16)
            fields[key] = ent
        ctk.CTkLabel(dlg, text=self.t("field.password")).pack(anchor="w", padx=16,
                                                              pady=(10, 0))
        secret = ctk.CTkEntry(dlg, width=320, show="•")
        secret.pack(padx=16)

        def save():
            VaultStore().add(fields["field.title"].get(), fields["field.username"].get(),
                             secret.get(), fields["field.url"].get())
            dlg.destroy()
            self._refresh_vault_list()
        ctk.CTkButton(dlg, text=self.t("btn.save"), command=save).pack(pady=16)

    # ====================================================== LOGIN & CHROME
    def _build_login_chrome(self, t) -> None:
        ctk.CTkLabel(t, text=self.t("login.title"),
                     font=("", 16, "bold")).pack(pady=(12, 2))
        ctk.CTkLabel(t, justify="left", text_color="gray",
                     text=self.t("login.intro")).pack(pady=(0, 8))

        steps = ctk.CTkTextbox(t, height=210, width=700)
        steps.pack(padx=12)
        steps.insert("1.0", LOGIN_STEPS.get(self.lang, LOGIN_STEPS["en"]))
        steps.configure(state="disabled")

        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkButton(row, text=self.t("btn.check_pc"), width=150,
                      command=self._check_hello).grid(row=0, column=0, padx=5)
        ctk.CTkButton(row, text=self.t("btn.signin_settings"), width=220,
                      command=win_hello.open_signin_settings).grid(row=0, column=1, padx=5)
        ctk.CTkButton(row, text=self.t("btn.chrome_pw"), width=170, fg_color="gray30",
                      command=win_hello.open_chrome_password_settings).grid(
            row=0, column=2, padx=5)

        self.hello_result = ctk.CTkLabel(t, text="", justify="left", wraplength=700)
        self.hello_result.pack(pady=(4, 2), padx=12, anchor="w")

    def _check_hello(self) -> None:
        self.hello_result.configure(text=self.t("login.checking"))

        def work():
            st = win_hello.detect()
            cams = ", ".join(st.cameras) or self.t("login.none")
            ir = (self.t("login.ir_yes", names=", ".join(st.ir_cameras))
                  if st.ir_cameras else self.t("login.ir_no"))
            txt = (f"{self.t('login.cameras')}: {cams}\n"
                   f"{self.t('login.ir_label')}: {ir}\n\n{st.note}")
            self.after(0, lambda: self.hello_result.configure(text=txt))
        threading.Thread(target=work, daemon=True).start()

    # ============================================================ SETTINGS
    def _build_settings(self, t) -> None:
        wrap = ctk.CTkScrollableFrame(t, height=500)
        wrap.pack(fill="both", expand=True)

        ctk.CTkLabel(wrap, text=self.t("settings.language")).pack(anchor="w", padx=12,
                                                                  pady=(8, 0))
        self._lang_menu = ctk.CTkOptionMenu(wrap, values=list(i18n.LANGUAGES.values()))
        self._lang_menu.set(i18n.LANGUAGES[self.lang])
        self._lang_menu.pack(anchor="w", padx=12)

        self._sw_liveness = self._switch(wrap, self.t("settings.liveness"),
                                         self.cfg.liveness_enabled)
        self._sw_adaptive = self._switch(wrap, self.t("settings.adaptive"),
                                         self.cfg.adaptive_update)
        self._sw_vault = self._switch(wrap, self.t("settings.vault_enable"),
                                      self.cfg.enable_vault)
        self._sw_keep = self._switch(wrap, self.t("settings.keep_model"),
                                     self.cfg.keep_model_loaded)

        self._slider(wrap, self.t("settings.threshold"),
                     0.20, 0.60, self.cfg.match_threshold, "thr_val")
        self._slider(wrap, self.t("settings.autolock"),
                     30, 600, self.cfg.vault_autolock_seconds, "lock_val", integer=True)

        ctk.CTkLabel(wrap, text=self.t("settings.challenge")).pack(anchor="w", padx=12,
                                                                   pady=(10, 0))
        self._challenge_vals = ["blink", "turn", "nod", "motion"]
        self._challenge = ctk.CTkOptionMenu(
            wrap, values=[self.t("challenge." + c) for c in self._challenge_vals])
        self._challenge.set(self.t("challenge." + self.cfg.liveness_challenge))
        self._challenge.pack(anchor="w", padx=12)

        ctk.CTkLabel(wrap, text=self.t("settings.camera_index")).pack(anchor="w",
                                                                      padx=12, pady=(10, 0))
        self._cam_idx = ctk.CTkEntry(wrap, width=80)
        self._cam_idx.insert(0, str(self.cfg.camera_index))
        self._cam_idx.pack(anchor="w", padx=12)

        ctk.CTkButton(wrap, text=self.t("btn.save_settings"), command=self._save_settings,
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
        # map language display name back to code
        new_lang = next((c for c, name in i18n.LANGUAGES.items()
                         if name == self._lang_menu.get()), self.lang)
        # map challenge display back to code
        chosen_challenge = next(
            (c for c in self._challenge_vals
             if self.t("challenge." + c) == self._challenge.get()),
            self.cfg.liveness_challenge)
        self.cfg.apply(
            language=new_lang,
            liveness_enabled=bool(self._sw_liveness.get()),
            adaptive_update=bool(self._sw_adaptive.get()),
            enable_vault=bool(self._sw_vault.get()),
            keep_model_loaded=bool(self._sw_keep.get()),
            match_threshold=round(float(self.thr_val.get()), 3),
            vault_autolock_seconds=int(self.lock_val.get()),
            liveness_challenge=chosen_challenge,
            camera_index=cam,
        )
        if new_lang != self.lang:
            self.lang = new_lang
            self._rebuild_ui()
            return
        self.settings_msg.configure(text=self.t("settings.saved"))
        self._refresh_status()

    # =============================================================== ABOUT
    def _build_about(self, t) -> None:
        box = ctk.CTkTextbox(t, width=720, height=500)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", ABOUT_TEXT.get(self.lang, ABOUT_TEXT["en"]).format(
            ver=__version__))
        box.configure(state="disabled")
        ctk.CTkButton(t, text=self.t("btn.project_page"), command=lambda: webbrowser.open(
            "https://github.com/Yeobi0318/VeriFace")).pack(pady=6)

    # =============================================================== close
    def _on_close(self) -> None:
        self._pumping = False
        self._stop_session()
        self.destroy()


LOGIN_STEPS = {
    "ko": """얼굴로 PIN을 대체하는 방법 - 안전하고 지원되는 방식:

[Windows 로그인 화면]
  1. 아래 "Windows 로그인 설정"을 눌러 설정 > 계정 > 로그인 옵션으로 이동.
  2. "얼굴 인식(Windows Hello)" > 설정 을 열고 안내를 따릅니다.
  3. 이후 잠금 화면이 PIN 대신 얼굴을 인식합니다.
     (Windows는 복구용으로 PIN을 함께 유지합니다 - 잠금 사고를 막는 안전장치입니다.)

[크롬 비밀번호]
  1. 먼저 위의 Windows Hello Face를 설정합니다.
  2. 아래 "크롬 비밀번호"를 눌러 설정에서
     "비밀번호를 채울 때 Windows Hello 사용"을 켭니다.
  3. 이제 크롬이 비밀번호를 보여주기/채우기 전에 얼굴로 확인합니다.

[왜 VeriFace가 직접 PIN을 대신 입력하지 않나요?]
  • Windows 로그인/UAC는 "보안 데스크톱"에서 동작해 일반 프로그램이 키 입력을
    보낼 수 없습니다(악용 방지를 위한 OS 설계). 그래서 기술적으로 불가능합니다.
  • PIN을 저장해 두고 얼굴이 보이면 자동 입력하면, IR 없는 일반 웹캠은 '사진'으로
    속일 수 있어 사진 한 장으로 계정이 뚫립니다. 보안을 크게 약화시키므로 하지 않습니다.
  • 대신 OS가 제공하는 Windows Hello Face(정공법)로 연결합니다.

참고: Windows Hello Face는 IR 카메라가 필요합니다. "이 PC 점검"으로 확인하세요.
IR 카메라가 없으면 OS/크롬 얼굴 로그인은 이 PC에서 사용할 수 없고,
VeriFace 자체 얼굴 잠금과 금고는 그대로 사용할 수 있습니다.
""",
    "en": """Use your FACE instead of your PIN - the supported, secure way:

WINDOWS SIGN-IN
  1. Click "Windows sign-in settings" > Accounts > Sign-in options.
  2. Open "Facial recognition (Windows Hello)" > Set up and follow the wizard.
  3. The lock screen then recognises your face instead of asking the PIN.
     (Windows keeps your PIN as a recovery fallback - that is intentional.)

CHROME PASSWORDS
  1. Set up Windows Hello Face (above) first.
  2. Click "Chrome passwords" and turn ON
     "Use Windows Hello when filling passwords".
  3. Chrome then verifies you by face before revealing/filling a password.

WHY DOESN'T VERIFACE TYPE THE PIN FOR YOU?
  - The Windows logon/UAC run on the "secure desktop"; normal apps cannot send
    keystrokes there (an OS anti-malware design). So it is not possible.
  - Storing your PIN and auto-typing it on a webcam match would let a photo
    unlock your whole account (an RGB webcam is photo-spoofable). It badly
    weakens security, so VeriFace does not do it.
  - Instead it points you to Windows Hello Face, the supported path.

NOTE: Windows Hello Face needs an IR camera. Use "Check this PC" to see whether
yours has one. Without it, OS/Chrome face login is unavailable here - but
VeriFace's own face unlock and vault still work.
""",
}

ABOUT_TEXT = {
    "ko": """VeriFace {ver}  -  로컬 안면인식 인증 (연구 / 교육용)

하는 일
  - 오픈소스 로컬 AI(YuNet + SFace, OpenCV Zoo)로 본인을 인식합니다.
  - 모든 처리는 오프라인 - 이미지·특징값이 PC를 벗어나지 않습니다.
  - 얼굴 템플릿과 금고는 Windows DPAPI로 현재 계정에 묶여 암호화됩니다.
  - 카메라와 AI 모델은 인식 중에만 올라가고 끝나면 즉시 해제됩니다.
  - 외형 변화(나이 등)를 반영: 확신도 높은 인식에서만 템플릿을 조금씩 갱신합니다.

솔직한 보안 안내
  - 편의·연구용 도구이며 인증 보안 제품이 아닙니다.
  - 라이브니스는 기초 수준(눈 깜박임/고개 움직임 + 텍스처)입니다. 사진 공격은 막지만
    정교한 영상 재생 공격까지는 막지 못합니다.
  - Windows 로그인 화면을 대체하거나 크롬에 개입하지 않습니다. 얼굴로 OS/크롬 로그인은
    "로그인·크롬" 탭의 Windows Hello Face를 사용하세요(IR 카메라 필요).
  - 금고는 브라우저 비밀번호를 내보내는 대신 쓰는 안전한 대안입니다.
  - 생체정보는 유출되면 바꿀 수 없습니다. Windows 암호/PIN을 실질적 대체재로 유지하세요.
""",
    "en": """VeriFace {ver}  -  local face authentication (research / educational)

WHAT IT DOES
  - Recognises YOU with open-source local AI (YuNet + SFace, OpenCV Zoo).
  - Everything runs offline; no image or embedding leaves this PC.
  - Face templates and the vault are DPAPI-encrypted, bound to your account.
  - Camera and model load only during a session and are released right after.
  - Adapts to appearance change (ageing): updates the template only from
    very confident, live matches.

HONEST SECURITY NOTES
  - A convenience + research tool, not a certified security product.
  - Liveness is basic (eye blink / head motion + texture). It stops casual
    photo attacks but not a determined video-replay attacker.
  - Does NOT replace the Windows logon or hook Chrome. For OS/Chrome face login
    use Windows Hello Face in the "Login & Chrome" tab (needs an IR camera).
  - The vault is a safe alternative to exporting browser passwords.
  - Biometrics cannot be changed if leaked. Keep a Windows password/PIN fallback.
""",
}


def main() -> None:
    app = VeriFaceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
