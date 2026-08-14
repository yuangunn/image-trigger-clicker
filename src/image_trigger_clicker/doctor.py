"""실행 전 환경 점검.

권한이 없으면 스크린샷이 검게 나오고, 아무것도 매칭되지 않는데 오류도 안 난다.
그 상태로 몇 시간을 돌리는 일이 없도록 미리 잡아준다.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
from pathlib import Path

from . import config as config_mod
from . import matcher, pg

__all__ = ["Check", "run_checks"]

_PRIVACY_PATH = "시스템 설정 > 개인정보 보호 및 보안"

_SCREEN_FIX = (
    f"{_PRIVACY_PATH} > 화면 기록 에서 이 명령을 실행한 터미널 앱\n"
    "(터미널.app / iTerm / VS Code 등)을 켜고, 그 앱을 완전히 종료 후 다시 여세요.\n"
    "권한은 itc 실행 파일이 아니라 '터미널 앱'에 부여됩니다."
)
_A11Y_FIX = (
    f"{_PRIVACY_PATH} > 손쉬운 사용 에서 이 명령을 실행한 터미널 앱을 켜세요.\n"
    "없으면 + 버튼으로 직접 추가하고, 앱을 완전히 종료 후 다시 여세요."
)


@dataclass(frozen=True)
class Check:
    """점검 항목 하나. ok는 True 정상 / False 문제 / None 판단 불가."""

    ok: bool | None
    title: str
    detail: str
    fix: str = ""


def _check_screen_recording() -> tuple[Check, float | None]:
    """스크린샷이 검은 화면인지로 화면 기록 권한을 판정하고, 배율도 함께 구한다."""
    try:
        shot = matcher.grab()
        logical = pg().size()
    except Exception as exc:
        # 어떤 이유로 실패했든 사용자에게는 해결 방법을 안내해야 한다.
        return (
            Check(False, "화면 기록 권한", f"스크린샷을 찍지 못했습니다 — {exc!r}", _SCREEN_FIX),
            None,
        )

    low, high = shot.convert("L").getextrema()
    scale = shot.width / int(logical[0]) if int(logical[0]) > 0 else 1.0

    if high <= 8:
        return (
            Check(
                False,
                "화면 기록 권한",
                f"스크린샷이 완전히 검은 화면입니다 (밝기 {low}~{high}). 권한이 없을 때 나오는 증상입니다.",
                _SCREEN_FIX,
            ),
            scale,
        )
    if high - low <= 4:
        return (
            Check(
                None,
                "화면 기록 권한",
                f"스크린샷이 거의 단색입니다 (밝기 {low}~{high}). "
                "권한 문제이거나 화면이 꺼져 있을 수 있습니다.",
                _SCREEN_FIX + "\n노트북 뚜껑을 덮었다면 열어두고 밝기만 최저로 내리세요.",
            ),
            scale,
        )
    return (
        Check(
            True,
            "화면 기록 권한",
            f"정상 (스크린샷 {shot.width}x{shot.height}, 밝기 {low}~{high})",
        ),
        scale,
    )


def _check_accessibility() -> Check:
    """손쉬운 사용(Accessibility) 권한.

    AXIsProcessTrusted()는 '지금 이 프로세스'를 기준으로 판정한다. itc를 실행한
    터미널 앱이 권한을 받았는지 그대로 알려주므로 우리가 원하는 바로 그 답이다.
    pyobjc에는 이 심볼이 없는 구성이 있어서 stdlib ctypes로 직접 부른다.
    """
    try:
        library = ctypes.util.find_library("ApplicationServices")
        if library is None:
            raise OSError("ApplicationServices 프레임워크를 찾지 못했습니다")
        app_services = ctypes.cdll.LoadLibrary(library)
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        app_services.AXIsProcessTrusted.argtypes = []
        trusted = bool(app_services.AXIsProcessTrusted())
    except Exception as exc:
        # macOS가 아니거나 프레임워크를 못 열었다. 수동 확인을 안내한다.
        return Check(
            None,
            "손쉬운 사용 권한",
            f"자동 확인 불가 ({exc}). 직접 확인하세요.",
            _A11Y_FIX,
        )

    if trusted:
        return Check(True, "손쉬운 사용 권한", "정상 (이 터미널 앱에 권한이 있습니다)")
    return Check(
        False,
        "손쉬운 사용 권한",
        "권한이 없습니다. 마우스 클릭이 무시될 수 있습니다.",
        _A11Y_FIX,
    )


def _check_display(scale: float | None) -> Check:
    if scale is None:
        return Check(None, "디스플레이 배율", "스크린샷 실패로 확인하지 못했습니다")
    try:
        logical = pg().size()
    except Exception as exc:
        return Check(None, "디스플레이 배율", f"화면 크기를 읽지 못했습니다 — {exc!r}")

    detail = (
        f"논리 {int(logical[0])}x{int(logical[1])} / "
        f"물리 {round(int(logical[0]) * scale)}x{round(int(logical[1]) * scale)}, 배율 {scale:g}x"
    )
    if abs(scale - round(scale)) > 0.01:
        return Check(
            None,
            "디스플레이 배율",
            detail + " — 배율이 정수가 아닙니다(스케일링 해상도). 좌표가 1~2픽셀 흔들릴 수 있습니다.",
            "디스플레이 해상도를 '기본값'으로 두면 매칭이 가장 안정적입니다.",
        )
    return Check(True, "디스플레이 배율", detail)


def _check_config(config_path: Path, profile_name: str | None) -> list[Check]:
    if not config_path.is_file():
        return [
            Check(
                False,
                "설정 파일",
                f"파일이 없습니다: {config_path}",
                "`itc init` 으로 샘플 설정을 만드세요.",
            )
        ]
    try:
        profile = config_mod.load(config_path, profile_name, check_images=False)
    except config_mod.ConfigError as exc:
        return [Check(False, "설정 파일", str(exc), "위 항목을 고친 뒤 다시 실행하세요.")]

    checks = [
        Check(
            True,
            "설정 파일",
            f"{config_path} — 프로파일 '{profile.name}', 대상 {len(profile.targets)}개, "
            f"주기 {profile.interval:g}초, 임계값 {profile.confidence:g}",
        )
    ]

    missing = config_mod.missing_images(profile)
    if missing:
        checks.append(
            Check(
                False,
                "트리거 이미지",
                "다음 파일이 없습니다:\n"
                + "\n".join(f"- '{t.name}' → {t.image}" for t in missing),
                "Cmd+Shift+4 로 영역을 캡처해 해당 경로에 저장하세요.\n"
                "설정의 상대 경로는 설정 파일이 있는 디렉터리 기준입니다.",
            )
        )
    else:
        checks.append(
            Check(True, "트리거 이미지", f"{len(profile.targets)}개 파일 모두 존재")
        )

    absolutes = [t for t in profile.targets if t.click.mode == "abs"]
    if absolutes:
        checks.append(
            Check(
                None,
                "클릭 방식",
                "절대 좌표(abs)를 쓰는 대상: " + ", ".join(f"'{t.name}'" for t in absolutes),
                "창이 조금만 움직여도 절대 좌표는 빗나가고, 무인 실행 중에는 아무도 못 알아챕니다.\n"
                "대상이 화면 정중앙에 고정 출력되는 경우가 아니면 offset 을 먼저 검토하세요.",
            )
        )
    return checks


def run_checks(config_path: Path, profile_name: str | None) -> list[Check]:
    """전체 점검을 실행하고 결과 목록을 돌려준다."""
    screen_check, scale = _check_screen_recording()
    return [
        screen_check,
        _check_accessibility(),
        _check_display(scale),
        *_check_config(config_path, profile_name),
    ]
