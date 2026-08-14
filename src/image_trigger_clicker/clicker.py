"""클릭 지점 계산과 실제 클릭.

계산된 좌표가 화면 밖이면 클릭하지 않는다. 무인 실행 중에 엉뚱한 곳을 누르는
사고는 되돌릴 수 없다.
"""

from __future__ import annotations

from . import pg
from .config import ClickSpec

__all__ = ["do_click", "in_bounds", "resolve_click"]


def resolve_click(click: ClickSpec, center: tuple[int, int]) -> tuple[int, int]:
    """어디를 누를지 계산한다 (전부 논리 좌표).

    이미지 중앙은 mode="center"일 때만 쓴다. 이미지는 "언제 누를지"를 판단하는
    트리거일 뿐이고, "어디를 누를지"는 설정에서 따로 정한다.
    """
    if click.mode == "abs":
        return click.x, click.y
    if click.mode == "offset":
        return center[0] + click.dx, center[1] + click.dy
    return center


def in_bounds(x: int, y: int, screen: tuple[int, int]) -> bool:
    """클릭 좌표가 화면 안인지. 밖이면 클릭을 건너뛴다."""
    width, height = screen
    return 0 <= x < width and 0 <= y < height


def do_click(x: int, y: int, *, dry_run: bool = False) -> None:
    """논리 좌표를 클릭한다. dry_run이면 아무것도 하지 않는다."""
    if dry_run:
        return
    pg().click(x, y)
