"""클릭 지점 계산과 화면 범위 검사 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from image_trigger_clicker import clicker
from image_trigger_clicker.clicker import do_click, in_bounds, resolve_click
from image_trigger_clicker.config import ClickSpec

CENTER = (500, 400)


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
def test_in_bounds(x: int, y: int, expected: bool) -> None:
    assert in_bounds(x, y, (1920, 1080)) is expected


def test_offset_can_leave_the_screen() -> None:
    # 화면 밖으로 나가는 계산 자체는 막지 않는다. 막는 쪽은 in_bounds 다.
    x, y = resolve_click(ClickSpec(mode="offset", dx=0, dy=900), (960, 1000))
    assert (x, y) == (960, 1900)
    assert in_bounds(x, y, (1920, 1080)) is False


def test_dry_run_does_not_touch_the_mouse(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr(clicker, "pg", lambda: fake)

    do_click(100, 200, dry_run=True)
    fake.click.assert_not_called()

    do_click(100, 200, dry_run=False)
    fake.click.assert_called_once_with(100, 200)
