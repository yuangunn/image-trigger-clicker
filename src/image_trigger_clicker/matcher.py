"""화면 캡처와 이미지 매칭.

레티나(HiDPI) 좌표 환산이 이 모듈의 존재 이유다.
pyautogui.screenshot()은 **물리 픽셀**로 이미지를 주고,
pyautogui.click()은 **논리 좌표**를 받는다. 레티나에서는 배율이 보통 2.0이라
환산을 빠뜨리면 클릭 좌표가 정확히 2배로 어긋난다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import pg

__all__ = [
    "Box",
    "count_matches",
    "detect_scale",
    "grab",
    "locate",
    "logical_center",
    "to_physical_region",
]


@dataclass(frozen=True)
class Box:
    """매칭 결과 사각형. 좌표·크기는 모두 물리 픽셀."""

    left: int
    top: int
    width: int
    height: int


def detect_scale() -> float:
    """스크린샷 가로(물리 픽셀) ÷ 화면 가로(논리 좌표) = 배율.

    레티나는 보통 2.0, 일반 모니터는 1.0.
    """
    shot = pg().screenshot()
    logical_width = int(pg().size()[0])
    if logical_width <= 0 or shot.width <= 0:
        return 1.0
    return shot.width / logical_width


def logical_center(box: Box, scale: float) -> tuple[int, int]:
    """물리 픽셀 매칭 결과의 중앙을 클릭에 쓸 논리 좌표로 환산한다."""
    if scale <= 0:
        scale = 1.0
    return (
        round((box.left + box.width / 2) / scale),
        round((box.top + box.height / 2) / scale),
    )


def to_physical_region(
    region: tuple[int, int, int, int] | None, scale: float
) -> tuple[int, int, int, int] | None:
    """설정의 region(사용자가 보는 논리 좌표)을 스크린샷의 물리 픽셀 영역으로 환산.

    설정 파일에 적는 좌표는 전부 논리 좌표로 통일한다 (`itc pos`가 보여주는 값과 같게).
    """
    if region is None:
        return None
    if scale <= 0:
        scale = 1.0
    left, top, width, height = region
    return (round(left * scale), round(top * scale), round(width * scale), round(height * scale))


def grab() -> Any:
    """현재 화면 스크린샷(물리 픽셀 PIL 이미지)."""
    return pg().screenshot()


def locate(
    image_path: Path | str,
    haystack: Any,
    confidence: float,
    region: tuple[int, int, int, int] | None = None,
) -> Box | None:
    """haystack 안에서 트리거 이미지를 찾는다. 못 찾으면 None.

    locateOnScreen(= 스크린샷 + locate)을 두 단계로 나눠 쓴다. 한 번 찍은 프레임으로
    여러 대상과 여러 임계값을 검사할 수 있어, 대상마다 화면을 다시 찍는 것보다
    빠르고 결과도 일관된다. region은 물리 픽셀이어야 한다.
    """
    try:
        box = pg().locate(str(image_path), haystack, confidence=confidence, region=region)
    except pg().ImageNotFoundException:
        # 못 찾은 것은 정상 상황이다. 예외로 루프를 깨지 않는다.
        return None
    if box is None:
        return None
    return Box(int(box.left), int(box.top), int(box.width), int(box.height))


def count_matches(
    image_path: Path | str,
    haystack: Any,
    confidence: float,
    region: tuple[int, int, int, int] | None = None,
    limit: int = 20,
) -> int:
    """임계값을 넘는 위치가 몇 곳인지 센다 (limit 까지만).

    매칭은 점수가 가장 높은 곳이 아니라 위에서부터 처음 만난 곳이 선택된다.
    그래서 후보가 여러 곳이면 정작 원하는 위치가 아닌 곳을 집을 수 있다.
    특징이 흐릿한 이미지(단색 배경, 완만한 그라데이션)를 트리거로 쓰면
    수백~수천 곳이 걸리기도 한다. `itc test` 가 이걸로 경고를 띄운다.
    """
    try:
        found = pg().locateAll(
            str(image_path), haystack, confidence=confidence, region=region, limit=limit
        )
        return sum(1 for _ in found)
    except pg().ImageNotFoundException:
        return 0
