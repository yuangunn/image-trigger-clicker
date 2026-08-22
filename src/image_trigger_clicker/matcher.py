"""화면 캡처와 이미지 매칭.

세 가지가 이 모듈의 존재 이유다.

1. **레티나 좌표 환산.** screenshot()은 물리 픽셀, click()은 논리 좌표라
   배율을 빠뜨리면 클릭 좌표가 배율만큼 어긋난다.
2. **최고 점수 매칭.** 임계값을 넘는 '첫' 위치가 아니라 '가장 닮은' 위치를 고른다.
   pyscreeze의 locate()는 전자를 준다 — 위에서부터 훑다가 처음 걸리는 곳을 돌려주므로,
   후보가 여럿이면 정작 원하는 위치가 아닌 곳을 집는다. 그래도 "매칭 성공"으로
   보이기 때문에 offset/center 모드에서 조용히 틀린 좌표를 계속 누르게 된다.
   그래서 cv2.matchTemplate을 직접 부르고 최고 점수 위치를 쓴다.
3. **가상 데스크톱 좌표계.** 모니터가 여러 대면 스크린샷은 전체를 이어붙인 한 장이고,
   논리 좌표 원점은 주 디스플레이가 아니라 가장 왼쪽·위 디스플레이 모서리다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import pg

__all__ = [
    "Display",
    "Match",
    "Screen",
    "count_candidates",
    "detect_screen",
    "grab",
    "locate",
]


@dataclass(frozen=True)
class Display:
    """모니터 한 대. 좌표·크기는 논리 좌표."""

    left: int
    top: int
    width: int
    height: int
    scale: float
    is_main: bool


@dataclass(frozen=True)
class Match:
    """매칭 결과. 좌표·크기는 물리 픽셀, score는 0~1 유사도."""

    left: int
    top: int
    width: int
    height: int
    score: float


@dataclass(frozen=True)
class Screen:
    """가상 데스크톱 전체. 좌표는 논리, scale은 스크린샷 물리 픽셀과의 비율."""

    left: int
    top: int
    width: int
    height: int
    scale: float
    displays: tuple[Display, ...] = ()

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def mixed_scales(self) -> bool:
        """모니터마다 배율이 다르면 True. 이 경우 단일 scale 환산이 부정확해진다."""
        return len({round(d.scale, 2) for d in self.displays}) > 1

    def to_logical(self, px: float, py: float) -> tuple[int, int]:
        """스크린샷 물리 픽셀 좌표 → 클릭에 쓸 논리 좌표."""
        scale = self.scale if self.scale > 0 else 1.0
        return (round(self.left + px / scale), round(self.top + py / scale))

    def to_physical_region(
        self, region: tuple[int, int, int, int] | None
    ) -> tuple[int, int, int, int] | None:
        """설정의 region(논리 좌표) → 스크린샷 안의 물리 픽셀 영역."""
        if region is None:
            return None
        scale = self.scale if self.scale > 0 else 1.0
        left, top, width, height = region
        return (
            round((left - self.left) * scale),
            round((top - self.top) * scale),
            round(width * scale),
            round(height * scale),
        )

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


def _displays() -> tuple[Display, ...]:
    """Quartz로 붙어 있는 모니터를 열거한다. 실패하면 빈 튜플."""
    try:
        import Quartz
    except Exception:  # macOS가 아니거나 pyobjc가 없다
        return ()
    err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
    if err or not count:
        return ()
    found = []
    for display_id in ids[:count]:
        bounds = Quartz.CGDisplayBounds(display_id)
        mode = Quartz.CGDisplayCopyDisplayMode(display_id)
        logical_width = Quartz.CGDisplayModeGetWidth(mode) if mode else 0
        pixel_width = Quartz.CGDisplayModeGetPixelWidth(mode) if mode else 0
        found.append(
            Display(
                left=round(bounds.origin.x),
                top=round(bounds.origin.y),
                width=round(bounds.size.width),
                height=round(bounds.size.height),
                scale=(pixel_width / logical_width) if logical_width else 1.0,
                is_main=bool(Quartz.CGDisplayIsMain(display_id)),
            )
        )
    return tuple(found)


def detect_screen(haystack: Any | None = None) -> Screen:
    """가상 데스크톱 크기와 배율을 알아낸다.

    haystack을 주면 그 스크린샷으로 배율을 재고, 없으면 한 장 찍는다.
    """
    shot = haystack if haystack is not None else grab()
    displays = _displays()

    if displays:
        left = min(d.left for d in displays)
        top = min(d.top for d in displays)
        right = max(d.left + d.width for d in displays)
        bottom = max(d.top + d.height for d in displays)
    else:
        # Quartz를 못 쓰면 주 디스플레이만 아는 pyautogui로 되돌아간다.
        size = pg().size()
        left, top = 0, 0
        right, bottom = int(size[0]), int(size[1])

    width = max(right - left, 1)
    scale = shot.width / width if shot.width else 1.0
    return Screen(left, top, width, max(bottom - top, 1), scale, displays)


def grab() -> Any:
    """현재 화면 스크린샷(물리 픽셀 PIL 이미지). 모니터가 여러 대면 전체를 담는다."""
    return pg().screenshot()


def _to_bgr(image: Any) -> Any:
    import numpy

    return numpy.array(image.convert("RGB"))[:, :, ::-1]


def _read_needle(image_path: Path | str) -> Any:
    """트리거 이미지를 BGR 배열로 읽는다.

    cv2.imread는 한글 파일명을 못 읽는 환경이 있어서 바이트로 읽어 디코딩한다.
    """
    import cv2
    import numpy

    data: Any = numpy.frombuffer(Path(image_path).read_bytes(), numpy.uint8)
    needle = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if needle is None:
        raise ValueError(f"이미지를 디코딩할 수 없습니다: {image_path}")
    return needle


def _correlate(
    image_path: Path | str, haystack: Any, region: tuple[int, int, int, int] | None
) -> tuple[Any, int, int, int, int]:
    """(유사도 맵, 트리거 너비, 트리거 높이, x오프셋, y오프셋).

    region은 물리 픽셀. 잘라서 계산한 뒤 오프셋을 되돌려 더할 수 있게 함께 돌려준다.
    """
    import cv2

    hay = _to_bgr(haystack)
    offset_x = offset_y = 0
    if region is not None:
        rx, ry, rw, rh = region
        rx, ry = max(rx, 0), max(ry, 0)
        hay = hay[ry : ry + rh, rx : rx + rw]
        offset_x, offset_y = rx, ry

    needle = _read_needle(image_path)
    nh, nw = needle.shape[:2]
    if hay.shape[0] < nh or hay.shape[1] < nw:
        raise ValueError(
            f"트리거 이미지({nw}x{nh})가 검사 영역({hay.shape[1]}x{hay.shape[0]})보다 큽니다"
        )
    return cv2.matchTemplate(hay, needle, cv2.TM_CCOEFF_NORMED), nw, nh, offset_x, offset_y


def locate(
    image_path: Path | str,
    haystack: Any,
    confidence: float,
    region: tuple[int, int, int, int] | None = None,
) -> Match | None:
    """haystack에서 가장 닮은 위치를 찾는다. 임계값에 못 미치면 None."""
    import cv2

    result, nw, nh, ox, oy = _correlate(image_path, haystack, region)
    _, best, _, best_at = cv2.minMaxLoc(result)
    if best < confidence:
        return None
    return Match(int(best_at[0]) + ox, int(best_at[1]) + oy, nw, nh, float(best))


def count_candidates(
    image_path: Path | str,
    haystack: Any,
    confidence: float,
    region: tuple[int, int, int, int] | None = None,
    limit: int = 20,
) -> int:
    """임계값을 넘는 '서로 겹치지 않는' 후보가 몇 곳인지 (limit까지만).

    1곳이 아니면 트리거 이미지가 그 화면에서 유일하지 않다는 뜻이다.
    최고 점수 위치를 고르므로 예전처럼 엉뚱한 곳을 집지는 않지만, 화면이 조금만
    바뀌어도 순위가 뒤집힐 수 있어 여전히 위험 신호다.
    """
    import cv2

    result, nw, nh, _, _ = _correlate(image_path, haystack, region)
    found = 0
    while found < limit:
        _, best, _, at = cv2.minMaxLoc(result)
        if best < confidence:
            break
        found += 1
        # 찾은 자리를 지워서 같은 덩어리가 여러 번 세어지지 않게 한다.
        x, y = at
        result[
            max(y - nh + 1, 0) : y + nh,
            max(x - nw + 1, 0) : x + nw,
        ] = -1.0
    return found
