"""클릭 지점 계산과 화면 범위 검사 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from image_trigger_clicker import clicker
from image_trigger_clicker.clicker import do_click, in_bounds, resolve_click
from image_trigger_clicker.config import ClickSpec
from image_trigger_clicker.matcher import Screen

CENTER = (500, 400)
SINGLE = Screen(left=0, top=0, width=1920, height=1080, scale=1.0)
# 주 디스플레이(0,0,1800x1169) 왼쪽에 1920x1080 모니터가 하나 더 붙은 구성
DUAL = Screen(left=-1920, top=0, width=3720, height=1169, scale=2.0)


def test_abs_ignores_image_position() -> None:
    # 절대 좌표는 이미지가 어디서 잡히든 같은 곳을 누른다.
    assert resolve_click(ClickSpec(mode="abs", x=960, y=640), CENTER) == (960, 640)
    assert resolve_click(ClickSpec(mode="abs", x=960, y=640), (0, 0)) == (960, 640)


def test_offset_moves_from_image_center() -> None:
    assert resolve_click(ClickSpec(mode="offset", dx=0, dy=40), CENTER) == (500, 440)
    assert resolve_click(ClickSpec(mode="offset", dx=-30, dy=-10), CENTER) == (470, 390)


def test_center_uses_image_center() -> None:
    assert resolve_click(ClickSpec(mode="center"), CENTER) == CENTER


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (0, 0, True),
        (1919, 1079, True),
        (960, 540, True),
        (1920, 540, False),  # 오른쪽 끝은 범위 밖
        (960, 1080, False),
        (-1, 540, False),
        (960, -1, False),
        (5000, 5000, False),
    ],
)
def test_in_bounds_single_monitor(x: int, y: int, expected: bool) -> None:
    assert in_bounds(x, y, SINGLE) is expected


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (-1920, 0, True),    # 왼쪽 모니터 왼쪽 위 끝
        (-1000, 500, True),  # 왼쪽 모니터 안 — 음수라고 막으면 안 된다
        (-1921, 500, False),
        (1799, 1168, True),
        (1800, 1168, False),
    ],
)
def test_in_bounds_allows_negative_coordinates_on_a_second_monitor(
    x: int, y: int, expected: bool
) -> None:
    assert in_bounds(x, y, DUAL) is expected


def test_offset_can_leave_the_screen() -> None:
    # 화면 밖으로 나가는 계산 자체는 막지 않는다. 막는 쪽은 in_bounds 다.
    x, y = resolve_click(ClickSpec(mode="offset", dx=0, dy=900), (960, 1000))
    assert (x, y) == (960, 1900)
    assert in_bounds(x, y, SINGLE) is False


def test_dry_run_does_not_touch_the_mouse(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr(clicker, "pg", lambda: fake)

    do_click(100, 200, dry_run=True)
    fake.click.assert_not_called()

    do_click(100, 200, dry_run=False)
    fake.click.assert_called_once_with(100, 200)
