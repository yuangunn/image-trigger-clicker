"""설정 파싱과 오류 메시지 테스트.

오류 메시지가 "어느 필드가 잘못됐는지"를 실제로 담고 있는지까지 확인한다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from image_trigger_clicker.config import (
    ClickSpec,
    ConfigError,
    Profile,
    load,
    missing_images,
    parse_document,
)

BASE = Path("/cfg")

VALID = """
[profiles.sample]
interval = 2.0
confidence = 0.85
click_delay = 0.3
region = [0, 0, 1920, 1080]

[[profiles.sample.targets]]
name = "확인 팝업"
image = "images/popup.png"
click = { mode = "abs", x = 960, y = 640 }
cooldown = 5.0

[[profiles.sample.targets]]
name = "다음 버튼"
image = "images/next.png"
click = { mode = "offset", dx = 0, dy = 40 }
"""


def parse(text: str, profile: str | None = None, base: Path = BASE) -> Profile:
    return parse_document(tomllib.loads(text), base, profile)


def test_parses_a_full_profile() -> None:
    profile = parse(VALID)
    assert profile.name == "sample"
    assert profile.interval == 2.0
    assert profile.confidence == 0.85
    assert profile.click_delay == 0.3
    assert profile.region == (0, 0, 1920, 1080)
    assert len(profile.targets) == 2

    first, second = profile.targets
    assert first.name == "확인 팝업"
    assert first.click == ClickSpec(mode="abs", x=960, y=640)
    assert first.cooldown == 5.0
    assert second.click == ClickSpec(mode="offset", dx=0, dy=40)
    assert second.cooldown == 0.0  # 생략하면 0


def test_defaults_when_omitted() -> None:
    profile = parse(
        """
        [profiles.p]
        [[profiles.p.targets]]
        name = "t"
        image = "a.png"
        click = { mode = "center" }
        """
    )
    assert (profile.interval, profile.confidence, profile.click_delay) == (2.0, 0.85, 0.0)
    assert profile.region is None
    assert profile.targets[0].click == ClickSpec(mode="center")


# --- 이미지 경로 ---------------------------------------------------------


def test_relative_image_is_resolved_against_config_dir() -> None:
    profile = parse(VALID)
    assert profile.targets[0].image == BASE / "images/popup.png"


def test_absolute_image_is_kept() -> None:
    profile = parse(
        """
        [profiles.p]
        [[profiles.p.targets]]
        name = "t"
        image = "/tmp/shot.png"
        click = { mode = "center" }
        """
    )
    assert profile.targets[0].image == Path("/tmp/shot.png")


# --- 프로파일 선택 -------------------------------------------------------


def test_single_profile_needs_no_name() -> None:
    assert parse(VALID).name == "sample"


def test_multiple_profiles_require_a_choice() -> None:
    text = VALID + (
        '\n[profiles.other]\n[[profiles.other.targets]]\n'
        'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
    )
    with pytest.raises(ConfigError) as exc:
        parse(text)
    assert "--profile" in str(exc.value)
    assert "default_profile" in str(exc.value)

    assert parse(text, "other").name == "other"
    assert parse('default_profile = "other"\n' + text).name == "other"


def test_unknown_profile_lists_available_ones() -> None:
    with pytest.raises(ConfigError, match="sample"):
        parse(VALID, "없는이름")


def test_no_profiles_at_all() -> None:
    with pytest.raises(ConfigError, match="profiles"):
        parse("interval = 1.0")


# --- 필드별 오류 ---------------------------------------------------------


def target(body: str) -> str:
    return f"[profiles.p]\n[[profiles.p.targets]]\n{body}\n"


def test_missing_click_names_the_field() -> None:
    with pytest.raises(ConfigError, match="click"):
        parse(target('name = "t"\nimage = "a.png"'))


def test_missing_image_names_the_field() -> None:
    with pytest.raises(ConfigError, match="image"):
        parse(target('name = "t"\nclick = { mode = "center" }'))


def test_unknown_click_mode_lists_valid_modes() -> None:
    with pytest.raises(ConfigError) as exc:
        parse(target('name = "t"\nimage = "a.png"\nclick = { mode = "middle" }'))
    message = str(exc.value)
    assert "middle" in message
    assert "abs" in message and "offset" in message and "center" in message


def test_abs_without_coordinates() -> None:
    with pytest.raises(ConfigError) as exc:
        parse(target('name = "t"\nimage = "a.png"\nclick = { mode = "abs", x = 10 }'))
    assert "'y'" in str(exc.value)


def test_offset_without_delta() -> None:
    with pytest.raises(ConfigError) as exc:
        parse(target('name = "t"\nimage = "a.png"\nclick = { mode = "offset", dx = 10 }'))
    assert "'dy'" in str(exc.value)


def test_abs_keys_rejected_in_offset_mode() -> None:
    with pytest.raises(ConfigError) as exc:
        parse(target('name = "t"\nimage = "a.png"\nclick = { mode = "offset", dx = 1, dy = 2, x = 3 }'))
    assert "'x'" in str(exc.value)


def test_typo_in_profile_key_is_rejected() -> None:
    # confidance = 0.9 가 조용히 무시되면 아무도 원인을 못 찾는다.
    with pytest.raises(ConfigError) as exc:
        parse(
            '[profiles.p]\nconfidance = 0.9\n[[profiles.p.targets]]\n'
            'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
        )
    assert "confidance" in str(exc.value)


def test_confidence_out_of_range() -> None:
    with pytest.raises(ConfigError, match="confidence"):
        parse(
            '[profiles.p]\nconfidence = 1.5\n[[profiles.p.targets]]\n'
            'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
        )


def test_interval_must_be_positive() -> None:
    with pytest.raises(ConfigError, match="interval"):
        parse(
            '[profiles.p]\ninterval = 0\n[[profiles.p.targets]]\n'
            'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
        )


def test_interval_must_be_a_number() -> None:
    with pytest.raises(ConfigError) as exc:
        parse(
            '[profiles.p]\ninterval = "2초"\n[[profiles.p.targets]]\n'
            'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
        )
    assert "interval" in str(exc.value) and "str" in str(exc.value)


@pytest.mark.parametrize(
    "region",
    ["[0, 0, 1920]", "[0, 0, 0, 1080]", "[-10, 0, 100, 100]", '"전체"'],
)
def test_bad_region(region: str) -> None:
    with pytest.raises(ConfigError, match="region"):
        parse(
            f'[profiles.p]\nregion = {region}\n[[profiles.p.targets]]\n'
            'name = "t"\nimage = "a.png"\nclick = { mode = "center" }\n'
        )


def test_targets_must_exist() -> None:
    with pytest.raises(ConfigError, match="targets"):
        parse("[profiles.p]\ninterval = 1.0")


def test_duplicate_target_names_rejected() -> None:
    with pytest.raises(ConfigError, match="중복"):
        parse(
            '[profiles.p]\n'
            '[[profiles.p.targets]]\nname = "같은이름"\nimage = "a.png"\nclick = { mode = "center" }\n'
            '[[profiles.p.targets]]\nname = "같은이름"\nimage = "b.png"\nclick = { mode = "center" }\n'
        )


# --- load(): 파일 단위 --------------------------------------------------


def test_load_reads_file_and_checks_images(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir()
    (tmp_path / "images/popup.png").write_bytes(b"x")
    (tmp_path / "images/next.png").write_bytes(b"x")
    config_path = tmp_path / "config.toml"
    config_path.write_text(VALID, encoding="utf-8")

    profile = load(config_path)
    assert profile.name == "sample"
    assert missing_images(profile) == []


def test_load_reports_missing_image_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(VALID, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load(config_path)
    assert "popup.png" in str(exc.value)

    # check_images=False 면 통과해야 한다 (doctor 가 이 경로로 진단한다).
    assert len(load(config_path, check_images=False).targets) == 2


def test_load_reports_toml_syntax_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[profiles.p\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="TOML"):
        load(config_path)


def test_load_missing_file_suggests_init(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="itc init"):
        load(tmp_path / "nope.toml")
