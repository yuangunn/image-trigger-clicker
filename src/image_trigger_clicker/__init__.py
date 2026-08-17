"""image-trigger-clicker — 화면 이미지를 트리거로 하는 범용 데스크톱 자동화 도구.

이미지는 "언제 누를지"만 판단한다. "어디를 누를지"는 설정에서 따로 지정한다.
이 분리가 이 도구의 핵심 설계다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["__version__", "pg"]

__version__ = "0.2.0"

_pyautogui: Any = None


def pg() -> Any:
    """pyautogui를 지연 임포트해서 돌려준다.

    pyautogui는 임포트하는 순간 화면 서버(Quartz)에 접근한다. 모듈 최상단에서
    임포트하면 GUI 없는 CI나 단위 테스트에서 "임포트만 해도" 실패한다.
    그래서 실제로 화면이 필요한 시점까지 미룬다. (sys.modules 캐시 덕에 두 번째
    호출부터는 사실상 공짜다.)
    """
    global _pyautogui
    if _pyautogui is None:
        import pyautogui

        # 긴급 정지: 마우스를 화면 왼쪽 위 모서리로 밀면 FailSafeException 발생.
        pyautogui.FAILSAFE = True
        _pyautogui = pyautogui
    return _pyautogui
