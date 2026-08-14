"""설정 파일(TOML) 파싱과 검증.

소스를 고치지 않고 설정만으로 쓸 수 있어야 하므로, 잘못된 설정은
"어느 필드가 왜 잘못됐는지"까지 말해주고 종료한다.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_CONFIG_PATH",
    "ClickSpec",
    "ConfigError",
    "Profile",
    "Target",
    "load",
    "missing_images",
    "parse_document",
    "profile_names",
    "resolve_config_path",
]

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "image-trigger-clicker"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_IMAGE_DIR = DEFAULT_CONFIG_DIR / "images"

CLICK_MODES = ("abs", "offset", "center")

_PROFILE_KEYS = {"interval", "confidence", "click_delay", "region", "targets"}
_TARGET_KEYS = {"name", "image", "click", "cooldown"}
_CLICK_KEYS = {
    "abs": {"mode", "x", "y"},
    "offset": {"mode", "dx", "dy"},
    "center": {"mode"},
}


class ConfigError(Exception):
    """설정이 잘못됐을 때. 메시지에 문제가 된 필드 경로가 들어간다."""


@dataclass(frozen=True)
class ClickSpec:
    """어디를 누를지.

    이미지 중앙 클릭은 mode="center"일 때뿐이며 기본 동작이 아니다.
    """

    mode: str
    x: int = 0
    y: int = 0
    dx: int = 0
    dy: int = 0

    def describe(self) -> str:
        if self.mode == "abs":
            return f"abs(x={self.x}, y={self.y})"
        if self.mode == "offset":
            return f"offset(dx={self.dx:+d}, dy={self.dy:+d})"
        return "center(이미지 중앙)"


@dataclass(frozen=True)
class Target:
    """감시 대상 하나. image가 트리거, click이 클릭 지점."""

    name: str
    image: Path
    click: ClickSpec
    cooldown: float = 0.0


@dataclass(frozen=True)
class Profile:
    """용도별 설정 묶음. 한 설정 파일에 여러 개를 둘 수 있다."""

    name: str
    interval: float
    confidence: float
    click_delay: float
    region: tuple[int, int, int, int] | None
    targets: tuple[Target, ...]


# --- 값 검증 헬퍼 ---------------------------------------------------------


def _require(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"{where}: '{key}' 항목이 없습니다")
    return table[key]


def _reject_unknown(table: dict[str, Any], allowed: set[str], where: str) -> None:
    """오타로 조용히 무시되는 설정을 막는다 (confidance = 0.9 같은 것)."""
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"{where}: 알 수 없는 항목 {', '.join(repr(k) for k in unknown)} "
            f"(쓸 수 있는 항목: {', '.join(sorted(allowed))})"
        )


def _as_float(value: Any, where: str, low: float | None, high: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: 숫자여야 하는데 {type(value).__name__} 입니다 ({value!r})")
    number = float(value)
    if low is not None and number < low:
        raise ConfigError(f"{where}: {low} 이상이어야 하는데 {number} 입니다")
    if high is not None and number > high:
        raise ConfigError(f"{where}: {high} 이하여야 하는데 {number} 입니다")
    return number


def _as_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: 정수여야 하는데 {type(value).__name__} 입니다 ({value!r})")
    return round(float(value))


def _as_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: 비어 있지 않은 문자열이어야 하는데 {value!r} 입니다")
    return value


def _as_table(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: 테이블([...])이어야 하는데 {type(value).__name__} 입니다")
    return value


def _parse_region(value: Any, where: str) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(f"{where}: [x, y, 너비, 높이] 형태의 숫자 4개여야 합니다 ({value!r})")
    left, top, width, height = (_as_int(v, f"{where}[{i}]") for i, v in enumerate(value))
    if width <= 0 or height <= 0:
        raise ConfigError(f"{where}: 너비와 높이는 0보다 커야 합니다 (너비={width}, 높이={height})")
    if left < 0 or top < 0:
        raise ConfigError(f"{where}: x, y는 0 이상이어야 합니다 (x={left}, y={top})")
    return left, top, width, height


def _parse_click(value: Any, where: str) -> ClickSpec:
    table = _as_table(value, f"{where} click")
    mode = _as_str(_require(table, "mode", f"{where} click"), f"{where} click.mode")
    if mode not in CLICK_MODES:
        raise ConfigError(
            f"{where} click.mode: '{mode}'는 알 수 없는 값입니다 "
            f"({', '.join(CLICK_MODES)} 중 하나여야 합니다)"
        )
    _reject_unknown(table, _CLICK_KEYS[mode], f"{where} click (mode='{mode}')")

    if mode == "abs":
        return ClickSpec(
            mode="abs",
            x=_as_int(_require(table, "x", f"{where} click (mode='abs')"), f"{where} click.x"),
            y=_as_int(_require(table, "y", f"{where} click (mode='abs')"), f"{where} click.y"),
        )
    if mode == "offset":
        return ClickSpec(
            mode="offset",
            dx=_as_int(
                _require(table, "dx", f"{where} click (mode='offset')"), f"{where} click.dx"
            ),
            dy=_as_int(
                _require(table, "dy", f"{where} click (mode='offset')"), f"{where} click.dy"
            ),
        )
    return ClickSpec(mode="center")


def _parse_target(value: Any, index: int, profile_name: str, base_dir: Path) -> Target:
    where = f"[[profiles.{profile_name}.targets]] {index + 1}번째"
    table = _as_table(value, where)
    name = _as_str(_require(table, "name", where), f"{where} name")

    # 이름을 알아낸 뒤부터는 사람이 알아보기 쉬운 이름으로 위치를 가리킨다.
    where = f"[[profiles.{profile_name}.targets]] '{name}'"
    _reject_unknown(table, _TARGET_KEYS, where)

    image = Path(_as_str(_require(table, "image", where), f"{where} image")).expanduser()
    if not image.is_absolute():
        image = base_dir / image

    return Target(
        name=name,
        image=image,
        click=_parse_click(_require(table, "click", where), where),
        cooldown=_as_float(table.get("cooldown", 0.0), f"{where} cooldown", 0.0, None),
    )


# --- 진입점 ---------------------------------------------------------------


def profile_names(document: dict[str, Any]) -> list[str]:
    profiles = document.get("profiles")
    return sorted(profiles) if isinstance(profiles, dict) else []


def parse_document(
    document: dict[str, Any], base_dir: Path, profile_name: str | None = None
) -> Profile:
    """이미 읽어들인 TOML 문서에서 프로파일 하나를 뽑아 검증한다.

    파일 시스템을 건드리지 않으므로 단위 테스트가 쉽다.
    base_dir는 상대 경로 이미지의 기준 디렉터리(보통 설정 파일이 있는 곳).
    """
    profiles_raw = document.get("profiles")
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ConfigError(
            "[profiles.<이름>] 프로파일이 하나도 없습니다 "
            "(`itc init` 으로 샘플 설정을 만들 수 있습니다)"
        )

    available = ", ".join(sorted(profiles_raw))
    name = profile_name or document.get("default_profile")
    if name is None:
        if len(profiles_raw) > 1:
            raise ConfigError(
                f"프로파일이 여러 개입니다 ({available}). "
                '--profile 로 고르거나 설정 파일 맨 위에 default_profile = "이름" 을 넣으세요'
            )
        name = next(iter(profiles_raw))
    if not isinstance(name, str):
        raise ConfigError(f"default_profile: 문자열이어야 하는데 {name!r} 입니다")
    if name not in profiles_raw:
        raise ConfigError(f"'{name}' 프로파일이 없습니다 (있는 프로파일: {available})")

    where = f"[profiles.{name}]"
    table = _as_table(profiles_raw[name], where)
    _reject_unknown(table, _PROFILE_KEYS, where)

    region_raw = table.get("region")
    targets_raw = table.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ConfigError(
            f"{where}: 감시 대상이 없습니다 "
            f"([[profiles.{name}.targets]] 블록이 최소 하나는 있어야 합니다)"
        )

    targets = tuple(
        _parse_target(raw, i, name, base_dir) for i, raw in enumerate(targets_raw)
    )
    counts = Counter(t.name for t in targets)
    duplicates = sorted(n for n, c in counts.items() if c > 1)
    if duplicates:
        raise ConfigError(
            f"{where}: 대상 이름이 중복됐습니다 ({', '.join(duplicates)}). "
            "쿨다운이 이름 기준이라 이름은 서로 달라야 합니다"
        )

    return Profile(
        name=name,
        interval=_as_float(table.get("interval", 2.0), f"{where} interval", 0.01, None),
        confidence=_as_float(table.get("confidence", 0.85), f"{where} confidence", 0.1, 1.0),
        click_delay=_as_float(table.get("click_delay", 0.0), f"{where} click_delay", 0.0, None),
        region=None if region_raw is None else _parse_region(region_raw, f"{where} region"),
        targets=targets,
    )


def resolve_config_path(path: str | Path | None) -> Path:
    """설정 파일 경로를 절대 경로로 정규화한다.

    이미지 상대 경로가 여기서 갈라지므로, 오류 메시지에 "어디를 찾았는지"가
    절대 경로로 나오게 해둔다.
    """
    chosen = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    return chosen if chosen.is_absolute() else Path.cwd() / chosen


def missing_images(profile: Profile) -> list[Target]:
    """이미지 파일이 실제로 없는 대상 목록."""
    return [t for t in profile.targets if not t.image.is_file()]


def load(
    path: str | Path | None = None,
    profile_name: str | None = None,
    *,
    check_images: bool = True,
) -> Profile:
    """설정 파일을 읽어 프로파일 하나를 돌려준다. 문제가 있으면 ConfigError."""
    config_path = resolve_config_path(path)
    if not config_path.is_file():
        raise ConfigError(
            f"설정 파일이 없습니다: {config_path}\n"
            "  `itc init` 으로 샘플 설정을 만들 수 있습니다"
        )
    try:
        document = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: TOML 문법 오류 — {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{config_path}: 파일을 읽을 수 없습니다 — {exc}") from exc

    parsed = parse_document(document, config_path.parent, profile_name)

    if check_images:
        missing = missing_images(parsed)
        if missing:
            lines = "\n".join(f"  - '{t.name}' → {t.image}" for t in missing)
            raise ConfigError(f"트리거 이미지 파일을 찾을 수 없습니다:\n{lines}")
    return parsed
