"""화면 영역 캡처와 클릭 녹화.

`itc capture` / `itc record` / `itc run --record-dir` 가 쓰는 저수준 도구들.
새 의존성은 없다 — macOS 기본 `screencapture` 와 이미 쓰고 있는 Quartz·Pillow만 쓴다.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matcher import Screen, grab

__all__ = ["ClickEvent", "annotate", "capture_region", "crop_around", "record_clicks"]


def capture_region(dest: Path) -> bool:
    """`screencapture -i` 로 영역을 고르게 해서 dest에 저장한다.

    사용자가 Esc로 취소하면 파일이 안 생기고 False를 돌려준다.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    # -i 대화형 선택, -x 소리 없음
    subprocess.run(["screencapture", "-i", "-x", str(dest)], check=False)
    return dest.exists() and dest.stat().st_size > 0


def crop_around(frame: Any, screen: Screen, x: int, y: int, size: tuple[int, int]) -> Any:
    """논리 좌표 (x, y)를 중심으로 프레임(물리 픽셀)에서 잘라낸다.

    size는 논리 좌표 기준 (너비, 높이).
    """
    scale = screen.scale if screen.scale > 0 else 1.0
    half_w = size[0] * scale / 2
    half_h = size[1] * scale / 2
    cx = (x - screen.left) * scale
    cy = (y - screen.top) * scale
    left = max(int(cx - half_w), 0)
    top = max(int(cy - half_h), 0)
    right = min(int(cx + half_w), frame.width)
    bottom = min(int(cy + half_h), frame.height)
    return frame.crop((left, top, right, bottom))


def annotate(frame: Any, screen: Screen, x: int, y: int, label: str = "") -> Any:
    """클릭 지점에 표시를 그린 사본. 실행 녹화용."""
    from PIL import ImageDraw

    out = frame.convert("RGB")
    draw = ImageDraw.Draw(out)
    scale = screen.scale if screen.scale > 0 else 1.0
    px = (x - screen.left) * scale
    py = (y - screen.top) * scale
    r = 22 * scale / 2
    draw.ellipse([px - r, py - r, px + r, py + r], outline=(255, 40, 40), width=max(int(scale * 2), 2))
    arm = r * 2
    draw.line([px - arm, py, px + arm, py], fill=(255, 40, 40), width=max(int(scale), 1))
    draw.line([px, py - arm, px, py + arm], fill=(255, 40, 40), width=max(int(scale), 1))
    if label:
        draw.text((px + r + 6, py - r), label, fill=(255, 40, 40))
    return out


@dataclass
class ClickEvent:
    """녹화된 클릭 하나."""

    x: int  # 논리 좌표
    y: int
    frame: Any  # 클릭 '직전' 스크린샷 (물리 픽셀)


def record_clicks(
    screen: Screen,
    on_click: Callable[[ClickEvent], None],
    *,
    poll: float = 0.35,
) -> None:
    """마우스 클릭을 기다렸다가 on_click을 부른다. Ctrl+C로 끝낼 때까지 계속.

    클릭 '직전' 화면이 필요하다(누르는 순간 화면이 바뀌므로). 그래서 poll초마다
    프레임을 하나 버퍼에 담아두고, 클릭이 오면 그 프레임을 쓴다.

    런루프는 CFRunLoopRun()이 아니라 짧은 CFRunLoopRunInMode()를 파이썬 루프에서
    반복 호출한다. 그래야 Ctrl+C(KeyboardInterrupt)가 전달된다 — CFRunLoopRun()은
    C 안에서 블록돼 시그널을 삼킨다.
    """
    import Quartz

    buffered: list[Any] = [grab()]

    def callback(proxy: Any, event_type: Any, event: Any, refcon: Any) -> Any:
        point = Quartz.CGEventGetLocation(event)
        on_click(ClickEvent(round(point.x), round(point.y), buffered[0]))
        return event

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown),
        callback,
        None,
    )
    if not tap:
        raise RuntimeError(
            "클릭을 감지할 수 없습니다. 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서\n"
            "  이 터미널 앱을 켜고, 앱을 완전히 종료 후 다시 여세요. (`itc doctor` 로 확인 가능)"
        )

    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopDefaultMode)
    Quartz.CGEventTapEnable(tap, True)

    last_frame_at = time.monotonic()
    try:
        while True:
            # 이 호출 안에서 콜백이 실행된다. 버퍼는 이 호출 '전'에만 갱신하므로
            # 콜백이 보는 프레임은 항상 클릭보다 앞선다.
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.05, False)
            now = time.monotonic()
            if now - last_frame_at >= poll:
                buffered[0] = grab()
                last_frame_at = now
    finally:
        Quartz.CGEventTapEnable(tap, False)
        Quartz.CFRunLoopRemoveSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopDefaultMode
        )
