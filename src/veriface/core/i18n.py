"""Tiny translation layer for the UI (Korean / English).

Every user-facing string in the GUI goes through :func:`t`. Core sessions emit
short *status codes* (e.g. ``"looking"``) rather than sentences, and the GUI
translates them, so the whole interface switches language cleanly.
"""
from __future__ import annotations

LANGUAGES = {"ko": "한국어", "en": "English"}

_S: dict[str, dict[str, str]] = {
    "subtitle": {
        "ko": "내 PC를 위한 로컬 안면인식 인증",
        "en": "Local face authentication for your own machine"},

    # tabs
    "tab.status": {"ko": "상태", "en": "Status"},
    "tab.analysis": {"ko": "PC 분석", "en": "PC Analysis"},
    "tab.enroll": {"ko": "얼굴 등록", "en": "Enroll"},
    "tab.vault": {"ko": "금고", "en": "Vault"},
    "tab.login": {"ko": "로그인·크롬", "en": "Login & Chrome"},
    "tab.settings": {"ko": "설정", "en": "Settings"},
    "tab.about": {"ko": "정보", "en": "About"},

    # status tab
    "status.template": {"ko": "얼굴 템플릿", "en": "Face template"},
    "status.models": {"ko": "AI 모델", "en": "AI models"},
    "status.profile": {"ko": "프로파일", "en": "Profile"},
    "status.liveness": {"ko": "라이브니스", "en": "Liveness"},
    "status.vault": {"ko": "금고", "en": "Vault"},
    "status.enrolled": {"ko": "등록됨 (샘플 {n}개)", "en": "Enrolled ({n} samples)"},
    "status.not_enrolled": {"ko": "미등록", "en": "Not enrolled"},
    "status.installed": {"ko": "설치됨", "en": "Installed"},
    "status.not_installed": {"ko": "미설치", "en": "Not installed"},
    "val.on": {"ko": "켜짐", "en": "on"},
    "val.off": {"ko": "꺼짐", "en": "off"},
    "val.enabled": {"ko": "사용", "en": "enabled"},
    "val.disabled": {"ko": "사용 안 함", "en": "disabled"},
    "btn.test_unlock": {"ko": "🔓  얼굴 잠금 해제 테스트", "en": "🔓  Test face unlock"},
    "btn.lock_windows": {"ko": "🔒  지금 Windows 잠그기", "en": "🔒  Lock Windows now"},
    "status.starting_camera": {"ko": "카메라 시작 중...", "en": "Starting camera..."},
    "status.unlock_ok": {"ko": "✅  인식 성공 (유사도 {score:.3f})",
                         "en": "✅  Recognised (score {score:.3f})"},
    "status.unlock_fail": {"ko": "❌  {msg} (유사도 {score:.3f})",
                           "en": "❌  {msg} (score {score:.3f})"},

    # analysis tab
    "analysis.title": {"ko": "이 PC를 분석해 최적 로컬 모델을 선택합니다",
                       "en": "Analyze this PC and pick the best local model"},
    "btn.analyze": {"ko": "🔍  PC 분석", "en": "🔍  PC Analysis"},
    "btn.install": {"ko": "⬇  추천 모델 설치", "en": "⬇  Install recommended models"},
    "analysis.analyzing": {"ko": "하드웨어 분석 중...", "en": "Analyzing hardware..."},
    "analysis.recommended": {"ko": "── 추천 프로파일 ──", "en": "── Recommended profile ──"},
    "analysis.hardware": {"ko": "── 하드웨어 ──", "en": "── Hardware ──"},
    "analysis.models_installed": {"ko": "모델 설치됨", "en": "Models installed"},
    "analysis.yes": {"ko": "예", "en": "yes"},
    "analysis.no_install": {"ko": "아니요 - 아래 설치 버튼을 누르세요",
                            "en": "NO - click Install below"},
    "install.already": {"ko": "이미 설치되어 있습니다.", "en": "Already installed."},
    "install.done": {"ko": "설치 완료: {names}", "en": "Installed: {names}"},
    "install.failed": {"ko": "설치 실패: {err}", "en": "Install failed: {err}"},

    # enroll tab
    "enroll.title": {"ko": "얼굴 등록", "en": "Enroll your face"},
    "enroll.tip": {"ko": "팁: 천천히 각도를 바꾸고, 정확도를 위해 안경 착용/미착용을 모두 담으세요.",
                   "en": "Tip: slowly change angle and enrol with and without glasses."},
    "enroll.preview": {"ko": "(카메라 미리보기)", "en": "(camera preview)"},
    "btn.start_enroll": {"ko": "▶  등록 시작", "en": "▶  Start enrollment"},
    "btn.cancel": {"ko": "■  취소", "en": "■  Cancel"},
    "btn.delete_template": {"ko": "🗑  템플릿 삭제", "en": "🗑  Delete template"},
    "enroll.models_missing": {"ko": "모델이 없습니다 - 먼저 PC 분석을 실행하세요.",
                              "en": "Models not installed - run PC Analysis first."},
    "enroll.saved": {"ko": "✅ 샘플 {n}개를 저장했습니다.", "en": "✅ Saved {n} samples."},
    "enroll.not_enough": {"ko": "❌ 샘플이 충분하지 않습니다. {msg}",
                          "en": "❌ Not enough samples captured. {msg}"},
    "enroll.deleted": {"ko": "템플릿을 삭제했습니다.", "en": "Template deleted."},

    # vault tab
    "vault.locked_title": {"ko": "🔒  금고가 잠겨 있습니다", "en": "🔒  Vault is locked"},
    "vault.unlock_hint": {"ko": "저장된 비밀번호를 보려면 얼굴로 잠금을 해제하세요.",
                          "en": "Unlock with your face to view saved passwords."},
    "btn.unlock_face": {"ko": "🔓  얼굴로 잠금 해제", "en": "🔓  Unlock with face"},
    "vault.disabled": {"ko": "설정에서 금고가 비활성화되어 있습니다.",
                       "en": "Vault is disabled in Settings."},
    "vault.enroll_first": {"ko": "먼저 얼굴을 등록하고 모델을 설치하세요.",
                           "en": "Enroll your face and install models first."},
    "vault.locked": {"ko": "잠김.", "en": "Locked."},
    "vault.unlocked_title": {"ko": "🔓 금고 열림", "en": "🔓 Vault unlocked"},
    "btn.lock": {"ko": "잠그기", "en": "Lock"},
    "btn.add": {"ko": "+ 추가", "en": "+ Add"},
    "vault.empty": {"ko": "저장된 비밀번호가 없습니다. + 추가를 누르세요.",
                    "en": "No saved passwords yet. Click + Add."},
    "btn.copy": {"ko": "복사", "en": "Copy"},
    "btn.delete": {"ko": "삭제", "en": "Delete"},
    "dialog.add_title": {"ko": "항목 추가", "en": "Add entry"},
    "field.title": {"ko": "제목", "en": "Title"},
    "field.username": {"ko": "사용자 이름", "en": "Username"},
    "field.url": {"ko": "주소(URL)", "en": "URL"},
    "field.password": {"ko": "비밀번호", "en": "Password / secret"},
    "btn.save": {"ko": "저장", "en": "Save"},

    # login & chrome tab
    "login.title": {"ko": "얼굴로 Windows·크롬 로그인",
                    "en": "Face login for Windows & Chrome"},
    "login.intro": {"ko": "PIN 대신 얼굴로 Windows 로그인과 크롬 비밀번호를 쓰는\n"
                          "안전하고 지원되는 방법은 Windows Hello Face 입니다.",
                    "en": "The secure, supported way to use your face instead of the PIN\n"
                          "for Windows sign-in AND Chrome passwords is Windows Hello Face."},
    "btn.check_pc": {"ko": "🔍  이 PC 점검", "en": "🔍  Check this PC"},
    "btn.signin_settings": {"ko": "⚙  Windows 로그인 설정", "en": "⚙  Windows sign-in settings"},
    "btn.chrome_pw": {"ko": "🌐  크롬 비밀번호", "en": "🌐  Chrome passwords"},
    "login.checking": {"ko": "카메라와 Hello 지원 여부 확인 중...",
                       "en": "Checking cameras and Hello capability..."},
    "login.cameras": {"ko": "카메라", "en": "Cameras"},
    "login.ir_label": {"ko": "IR 카메라 (Hello Face)", "en": "IR camera (Hello Face)"},
    "login.ir_yes": {"ko": "있음 - {names}", "en": "yes - {names}"},
    "login.ir_no": {"ko": "감지되지 않음", "en": "not detected"},
    "login.none": {"ko": "없음", "en": "none"},

    # settings tab
    "settings.language": {"ko": "언어 (Language)", "en": "Language"},
    "settings.liveness": {"ko": "라이브니스 / 위변조 방지",
                          "en": "Liveness / anti-spoofing"},
    "settings.vault_enable": {"ko": "비밀번호 금고 사용", "en": "Enable password vault"},
    "settings.keep_model": {"ko": "모델을 메모리에 유지 (빠르지만 RAM 더 사용)",
                            "en": "Keep model in memory (faster, more RAM)"},
    "settings.adaptive": {"ko": "외형 변화 자동 학습 (나이 변화 반영)",
                          "en": "Adapt to appearance changes over time (aging)"},
    "settings.threshold": {"ko": "일치 임계값 (높을수록 엄격)",
                           "en": "Match threshold (higher = stricter)"},
    "settings.autolock": {"ko": "금고 자동 잠금 (초)", "en": "Vault auto-lock (seconds)"},
    "settings.challenge": {"ko": "라이브니스 동작", "en": "Liveness challenge"},
    "settings.camera_index": {"ko": "카메라 번호", "en": "Camera index"},
    "btn.save_settings": {"ko": "💾  설정 저장", "en": "💾  Save settings"},
    "settings.saved": {"ko": "저장되었습니다.", "en": "Saved."},
    "challenge.blink": {"ko": "눈 깜박임", "en": "blink"},
    "challenge.turn": {"ko": "고개 돌리기", "en": "turn"},
    "challenge.nod": {"ko": "고개 끄덕이기", "en": "nod"},
    "challenge.motion": {"ko": "약간 움직이기", "en": "motion"},

    # about
    "btn.project_page": {"ko": "프로젝트 페이지", "en": "Project page"},

    # liveness hints (shown live)
    "hint.blink": {"ko": "천천히 한 번 깜박여 주세요", "en": "Please blink once, slowly"},
    "hint.turn": {"ko": "고개를 천천히 좌우로 돌려 주세요",
                  "en": "Slowly turn your head left, then right"},
    "hint.nod": {"ko": "고개를 천천히 끄덕여 주세요", "en": "Slowly nod your head up and down"},
    "hint.motion": {"ko": "카메라를 보며 약간 움직여 주세요",
                    "en": "Look at the camera and move slightly"},

    # live session status codes
    "st.position_face": {"ko": "얼굴을 화면 안에 맞춰 주세요",
                         "en": "Position your face in the frame"},
    "st.capturing": {"ko": "좋아요 - 천천히 각도를 바꿔 주세요 (안경 착용/미착용)",
                     "en": "Great - keep slowly changing your angle (glasses on/off)"},
    "st.looking": {"ko": "얼굴을 찾는 중...", "en": "Looking for your face..."},
    "st.not_recognized": {"ko": "인식 안 됨 - 정면을 보고 가만히 있어 주세요",
                          "en": "Not recognised - keep still and face the camera"},
    "st.recognized": {"ko": "인식됨", "en": "Recognised"},
    "st.match_challenge": {"ko": "일치 - {hint}", "en": "Match - {hint}"},
    "st.flat_image": {"ko": "이미지가 너무 평평합니다(사진/화면 의심) - 조명을 밝게 하고 가까이 오세요",
                      "en": "Image too flat (possible photo/screen) - move closer in good light"},
    "st.no_motion": {"ko": "자연스러운 움직임이 없습니다", "en": "No natural motion detected"},
    "st.need_frames": {"ko": "프레임이 더 필요합니다", "en": "Need more frames"},
    "st.live_ok": {"ko": "라이브니스 통과", "en": "Liveness OK"},

    # result messages
    "res.complete": {"ko": "등록이 완료되었습니다.", "en": "Enrollment complete."},
    "res.cancelled": {"ko": "취소되었습니다.", "en": "Cancelled."},
    "res.no_enroll": {"ko": "아직 등록된 얼굴이 없습니다.", "en": "No face is enrolled yet."},
    "res.timeout": {"ko": "시간 초과 - 얼굴을 인식하지 못했습니다.",
                    "en": "Timed out - face not recognised."},
    "res.recognized": {"ko": "얼굴을 인식했습니다.", "en": "Face recognised."},
}


def t(key: str, lang: str = "ko", **kw) -> str:
    entry = _S.get(key)
    if not entry:
        return key
    s = entry.get(lang) or entry.get("en") or key
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s
