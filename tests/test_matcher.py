"""레티나 좌표 환산 테스트.

이 환산을 빠뜨리면 클릭 좌표가 정확히 배율만큼 어긋난다. 화면 접근은 하지 않는다.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_trigger_clicker import matcher
from image_trigger_clicker.matcher import Box, count_matches, locate, logical_center, to_physical_region


class FakeNotFound(Exception):
    """pyautogui.ImageNotFoundException 대역."""


@pytest.fixture
def fake_pg(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.ImageNotFoundException = FakeNotFound
    monkeypatch.setattr(matcher, "pg", lambda: fake)
    return fake


def test_logical_center_no_scaling() -> None:
    assert logical_center(Box(100, 200, 80, 40), 1.0) == (140, 220)


def test_logical_center_retina_halves_coordinates() -> None:
    # 물리 픽셀 중앙 (140, 220)은 배율 2.0에서 논리 좌표 (70, 110)이다.
    assert logical_center(Box(100, 200, 80, 40), 2.0) == (70, 110)


def test_logical_center_retina_regression() -> None:
    # 환산을 빠뜨렸을 때 나오는 값(1040, 1040)이 아니어야 한다.
    assert logical_center(Box(1000, 1000, 80, 80), 2.0) == (520, 520)


def test_logical_center_fractional_scale() -> None:
    assert logical_center(Box(0, 0, 100, 100), 1.5) == (33, 33)


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_logical_center_bad_scale_falls_back_to_one(scale: float) -> None:
    assert logical_center(Box(100, 200, 80, 40), scale) == (140, 220)


def test_to_physical_region_scales_up() -> None:
    assert to_physical_region((0, 0, 1920, 1080), 2.0) == (0, 0, 3840, 2160)
    assert to_physical_region((10, 20, 100, 50), 2.0) == (20, 40, 200, 100)


def test_to_physical_region_identity_and_none() -> None:
    assert to_physical_region((10, 20, 100, 50), 1.0) == (10, 20, 100, 50)
    assert to_physical_region(None, 2.0) is None


# --- locate / count_matches (pyautogui 모킹) ------------------------------


def test_locate_returns_a_box(fake_pg: MagicMock) -> None:
    fake_pg.locate.return_value = SimpleNamespace(left=10, top=20, width=30, height=40)
    assert locate("a.png", object(), 0.9) == Box(10, 20, 30, 40)


def test_locate_swallows_image_not_found(fake_pg: MagicMock) -> None:
    # 못 찾는 것은 정상 상황이다. 예외가 루프 밖으로 새면 안 된다.
    fake_pg.locate.side_effect = FakeNotFound
    assert locate("a.png", object(), 0.9) is None


def test_locate_handles_none_return(fake_pg: MagicMock) -> None:
    # pyscreeze 버전에 따라 예외 대신 None 을 준다.
    fake_pg.locate.return_value = None
    assert locate("a.png", object(), 0.9) is None


def test_count_matches_counts_candidates(fake_pg: MagicMock) -> None:
    fake_pg.locateAll.return_value = iter([1, 2, 3])
    assert count_matches("a.png", object(), 0.9, limit=20) == 3
    assert fake_pg.locateAll.call_args.kwargs["limit"] == 20


def test_count_matches_returns_zero_when_absent(fake_pg: MagicMock) -> None:
    fake_pg.locateAll.side_effect = FakeNotFound
    assert count_matches("a.png", object(), 0.9) == 0
