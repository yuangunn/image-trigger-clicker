"""매칭과 좌표 환산 테스트.

locate/count_candidates 는 모킹하지 않고 실제 cv2 로 돌린다. 합성 이미지라
화면에 접근하지 않으므로 CI에서도 그대로 돌아가고, 진짜 매칭 동작을 검증한다.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PIL import Image

from image_trigger_clicker.matcher import (
    Display,
    Match,
    Screen,
    count_candidates,
    locate,
)

RETINA = Screen(left=0, top=0, width=900, height=600, scale=2.0)


def noise(width: int, height: int, seed: int) -> Image.Image:
    """고유한(특징이 뚜렷한) 패치."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (width, height))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(width * height)])
    return img


@pytest.fixture
def scene(tmp_path: Path) -> tuple[Image.Image, Path]:
    """(600x400 배경 + (400,300)에 진짜 패치, 트리거 이미지 경로)."""
    hay = Image.new("RGB", (600, 400), (20, 40, 60))
    patch = noise(60, 40, seed=7)
    hay.paste(patch, (400, 300))
    needle = tmp_path / "트리거.png"  # 한글 파일명도 읽혀야 한다
    patch.save(needle)
    return hay, needle


# --- Screen 좌표 환산 -----------------------------------------------------


def test_to_logical_halves_on_retina() -> None:
    assert RETINA.to_logical(140, 220) == (70, 110)


def test_to_logical_regression_without_scaling() -> None:
    # 환산을 빠뜨렸을 때 나오는 값(1040, 1040)이 아니어야 한다.
    assert RETINA.to_logical(1040, 1040) == (520, 520)


def test_to_logical_on_a_monitor_left_of_the_main_one() -> None:
    # 주 디스플레이 왼쪽 모니터는 논리 좌표가 음수다.
    screen = Screen(left=-1920, top=0, width=3720, height=1169, scale=2.0)
    assert screen.to_logical(0, 0) == (-1920, 0)
    assert screen.to_logical(3840, 0) == (0, 0)


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_bad_scale_falls_back_to_one(scale: float) -> None:
    assert Screen(0, 0, 900, 600, scale).to_logical(140, 220) == (140, 220)


def test_to_physical_region() -> None:
    assert RETINA.to_physical_region((10, 20, 100, 50)) == (20, 40, 200, 100)
    assert RETINA.to_physical_region(None) is None
    shifted = Screen(left=-1920, top=0, width=3720, height=1169, scale=2.0)
    assert shifted.to_physical_region((-1920, 0, 100, 100)) == (0, 0, 200, 200)


def test_contains_uses_virtual_desktop() -> None:
    screen = Screen(left=-1920, top=0, width=3720, height=1169, scale=2.0)
    assert screen.contains(-1000, 500)      # 왼쪽 모니터 = 음수 좌표도 유효
    assert not screen.contains(-2000, 500)
    assert screen.contains(1799, 1168)
    assert not screen.contains(1800, 1168)  # right 는 배타적


def test_mixed_scales() -> None:
    same = (Display(0, 0, 100, 100, 2.0, True), Display(100, 0, 100, 100, 2.0, False))
    diff = (Display(0, 0, 100, 100, 2.0, True), Display(100, 0, 100, 100, 1.0, False))
    assert not Screen(0, 0, 200, 100, 2.0, same).mixed_scales
    assert Screen(0, 0, 200, 100, 2.0, diff).mixed_scales


# --- locate: 최고 점수를 고르는가 ------------------------------------------


def test_locate_finds_the_patch(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    match = locate(needle, hay, 0.9)
    assert match == Match(400, 300, 60, 40, pytest.approx(1.0, abs=1e-6))


def test_locate_prefers_the_best_match_over_an_earlier_decoy(
    scene: tuple[Image.Image, Path], tmp_path: Path
) -> None:
    """이 프로젝트에서 실제로 겪은 버그의 회귀 테스트.

    pyscreeze 는 임계값을 넘는 '첫' 위치(가장 위·왼쪽)를 돌려줘서, 더 닮은 곳을
    두고 미끼를 집었다. 최고 점수를 골라야 한다.
    """
    hay, needle = scene
    # 진짜보다 살짝 덜 닮은 미끼를, raster 순서상 훨씬 앞쪽에 둔다.
    decoy = Image.blend(Image.open(needle).convert("RGB"), noise(60, 40, seed=3), 0.14)
    hay.paste(decoy, (50, 50))

    match = locate(needle, hay, 0.7)
    assert match is not None
    assert (match.left, match.top) == (400, 300), "미끼를 집었습니다"
    assert match.score > 0.999


def test_locate_returns_none_below_threshold(
    scene: tuple[Image.Image, Path], tmp_path: Path
) -> None:
    hay, _ = scene
    other = tmp_path / "other.png"
    noise(60, 40, seed=99).save(other)
    assert locate(other, hay, 0.9) is None


def test_locate_region_offset_is_restored(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    match = locate(needle, hay, 0.9, (380, 280, 120, 100))
    assert match is not None
    assert (match.left, match.top) == (400, 300)


def test_locate_outside_region_is_not_found(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    assert locate(needle, hay, 0.9, (0, 0, 200, 200)) is None


def test_needle_bigger_than_region_is_a_clear_error(
    scene: tuple[Image.Image, Path]
) -> None:
    hay, needle = scene
    with pytest.raises(ValueError, match="보다 큽니다"):
        locate(needle, hay, 0.9, (0, 0, 30, 20))


# --- count_candidates: 겹치는 후보를 한 번만 센다 --------------------------


def test_count_candidates_counts_distinct_places(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    assert count_candidates(needle, hay, 0.9) == 1

    hay.paste(Image.open(needle).convert("RGB"), (100, 100))
    assert count_candidates(needle, hay, 0.9) == 2


def test_count_candidates_respects_limit(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    patch = Image.open(needle).convert("RGB")
    for x in range(0, 300, 70):
        hay.paste(patch, (x, 0))
    assert count_candidates(needle, hay, 0.9, None, limit=2) == 2


def test_count_candidates_zero_when_absent(scene: tuple[Image.Image, Path]) -> None:
    hay, needle = scene
    assert count_candidates(needle, hay, 0.999999, (0, 0, 300, 200)) == 0
