"""명령줄 진입점. `itc <서브커맨드>`."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from . import __version__, clicker, config, doctor, matcher, pg
from .logging import close_log_file, error, log, open_log_file, warn

__all__ = ["main"]

# itc test 가 훑는 임계값. 높은 값부터 내려가며 처음 잡히는 지점을 찾는다.
CONFIDENCE_STEPS = (0.95, 0.90, 0.85, 0.80, 0.75, 0.70)

HEARTBEAT_EVERY = 60  # 검사 몇 회마다 생존 확인 로그를 남길지

# itc test 가 "매칭 위치가 여러 곳"을 경고할 때 세는 상한.
AMBIGUITY_LIMIT = 20

SAMPLE_CONFIG = '''# image-trigger-clicker 설정 파일
#
# 화면에 지정한 이미지가 나타나면, 미리 정해둔 좌표를 클릭한다.
# 핵심: 이미지는 "언제 누를지"를 판단하는 트리거일 뿐이다.
#       "어디를 누를지"는 아래 click 에서 따로 정한다.
#
# 좌표는 전부 논리 좌표(= `itc pos` 가 보여주는 값)로 적는다.

# --profile 을 생략했을 때 쓸 프로파일. 프로파일이 하나뿐이면 없어도 된다.
default_profile = "sample"


# ── 프로파일 ──────────────────────────────────────────────────────────────
# 용도별로 여러 개를 둘 수 있다:  itc run --profile <이름>
[profiles.sample]
interval    = 2.0     # 검사 주기(초)
confidence  = 0.85    # 매칭 임계값 0~1. 높을수록 엄격. `itc test` 로 튜닝한다.
click_delay = 0.3     # 매칭 후 클릭까지 기다릴 시간(초)
# region    = [0, 0, 1920, 1080]   # 감시 영역 [x, y, 너비, 높이]. 생략하면 전체 화면.
                                   # 영역을 좁히면 검사가 빨라지고 오탐도 준다.


# ── 감시 대상 ─────────────────────────────────────────────────────────────
[[profiles.sample.targets]]
name     = "확인 팝업"
image    = "images/popup.png"   # 설정 파일이 있는 디렉터리 기준 상대 경로. 절대 경로도 된다.
cooldown = 5.0                  # 이 대상을 누른 뒤 재클릭을 막을 시간(초)

# click 지정 방식은 셋 중 하나:
#   { mode = "abs",    x = 960, y = 640 }   사전 설정된 절대 좌표
#   { mode = "offset", dx = 0, dy = 40 }    찾은 이미지 중앙 기준 상대 이동
#   { mode = "center" }                     찾은 이미지 중앙
#
# abs 보다 offset 을 먼저 검토할 것. 창을 조금만 옮겨도 절대 좌표는 빗나가는데
# 무인 실행 중에는 아무도 알아채지 못한다. 대상이 화면 정중앙에 고정 출력되는
# 경우에만 abs 를 쓴다.
click = { mode = "offset", dx = 0, dy = 40 }

# 감시 대상은 여러 개 등록할 수 있다. 주석을 풀어서 쓰면 된다.
# [[profiles.sample.targets]]
# name     = "다음 버튼"
# image    = "images/next.png"
# cooldown = 3.0
# click    = { mode = "center" }


# ── 다른 용도의 프로파일 예시 ─────────────────────────────────────────────
# [profiles.strict]
# interval    = 1.0
# confidence  = 0.93
# click_delay = 0.0
#
# [[profiles.strict.targets]]
# name  = "오류 대화상자"
# image = "images/error.png"
# click = { mode = "abs", x = 960, y = 640 }
'''


# --- run -----------------------------------------------------------------


def _log_startup(profile: config.Profile, screen: tuple[int, int], scale: float, dry_run: bool) -> None:
    log(f"image-trigger-clicker {__version__} 시작" + (" (DRY-RUN: 클릭하지 않습니다)" if dry_run else ""))
    log(
        f"화면: 논리 {screen[0]}x{screen[1]} / "
        f"물리 {round(screen[0] * scale)}x{round(screen[1] * scale)}, 배율 {scale:g}x"
    )
    log(
        f"프로파일 '{profile.name}' — 주기 {profile.interval:g}초, "
        f"임계값 {profile.confidence:g}, 클릭 지연 {profile.click_delay:g}초"
    )
    log(f"감시 영역: {'전체 화면' if profile.region is None else str(list(profile.region))}")
    log(f"감시 대상 {len(profile.targets)}개:")
    for i, target in enumerate(profile.targets, 1):
        log(
            f"  {i}. '{target.name}' ← {target.image.name} | "
            f"클릭 {target.click.describe()} | 쿨다운 {target.cooldown:g}초"
        )
    log("긴급 정지: 마우스를 화면 왼쪽 위 모서리로 (FailSafe) 또는 Ctrl+C")


def _scan_once(
    profile: config.Profile,
    region: tuple[int, int, int, int] | None,
    scale: float,
    screen: tuple[int, int],
    last_click: dict[str, float],
    out_of_bounds: set[str],
    dry_run: bool,
) -> int:
    """화면을 한 번 찍어 모든 대상을 검사한다. 이번에 클릭한 횟수를 돌려준다."""
    haystack = matcher.grab()
    performed = 0

    for target in profile.targets:
        since = time.monotonic() - last_click.get(target.name, float("-inf"))
        if since < target.cooldown:
            continue

        box = matcher.locate(target.image, haystack, profile.confidence, region)
        if box is None:
            continue

        center = matcher.logical_center(box, scale)
        x, y = clicker.resolve_click(target.click, center)

        # 계산된 좌표가 화면 밖이면 절대 누르지 않는다.
        # 매 주기 같은 경고를 쏟아내면 장시간 로그가 못 쓰게 되므로, 범위 밖으로
        # "들어간 순간"에만 남기고 다시 안으로 들어오면 상태를 푼다.
        if not clicker.in_bounds(x, y, screen):
            if target.name not in out_of_bounds:
                out_of_bounds.add(target.name)
                warn(
                    f"'{target.name}' 클릭 지점 x={x} y={y} 이(가) 화면 "
                    f"{screen[0]}x{screen[1]} 밖입니다. 클릭하지 않고 건너뜁니다"
                    " (같은 경고는 범위 안으로 돌아올 때까지 생략)"
                )
            continue
        out_of_bounds.discard(target.name)

        log(
            f"매칭: '{target.name}' 이미지 중앙 x={center[0]} y={center[1]} → "
            f"{profile.click_delay:g}초 후 {target.click.describe()}"
        )
        if profile.click_delay > 0:
            time.sleep(profile.click_delay)

        clicker.do_click(x, y, dry_run=dry_run)
        log(f"{'[DRY-RUN] 클릭 생략' if dry_run else '클릭'}: '{target.name}' x={x} y={y}")
        last_click[target.name] = time.monotonic()
        performed += 1

    return performed


def cmd_run(args: argparse.Namespace) -> int:
    profile = config.load(args.config, args.profile)
    if args.log_file:
        open_log_file(Path(args.log_file))

    scale = matcher.detect_scale()
    size = pg().size()
    screen = (int(size[0]), int(size[1]))
    region = matcher.to_physical_region(profile.region, scale)
    _log_startup(profile, screen, scale, args.dry_run)

    checks = 0
    clicks = 0
    last_click: dict[str, float] = {}
    out_of_bounds: set[str] = set()

    try:
        while True:
            checks += 1
            try:
                clicks += _scan_once(
                    profile, region, scale, screen, last_click, out_of_bounds, args.dry_run
                )
            except pg().FailSafeException:
                raise
            except Exception as exc:
                # 무인 실행이 전제라 절대 죽으면 안 된다. 로그만 남기고 다음 주기로.
                warn(f"검사 중 오류가 났지만 계속 진행합니다 — {exc!r}")

            if checks % HEARTBEAT_EVERY == 0:
                log(f"생존 확인 — 누적 검사 {checks}회, 클릭 {clicks}회")
            time.sleep(profile.interval)

    except KeyboardInterrupt:
        print()
        log("Ctrl+C — 종료합니다")
    except pg().FailSafeException:
        log("긴급 정지(FailSafe): 마우스가 화면 모서리에 닿아 중단합니다")
    finally:
        log(f"정리 완료 — 총 검사 {checks}회, 클릭 {clicks}회")
        close_log_file()
    return 0


# --- pos -----------------------------------------------------------------


def cmd_pos(_args: argparse.Namespace) -> int:
    size = pg().size()
    print(f"화면 크기(논리 좌표): {int(size[0])}x{int(size[1])}")
    print("클릭할 지점에 마우스를 올려두고 값을 읽으세요. Ctrl+C 로 종료합니다.\n")
    try:
        while True:
            x, y = pg().position()
            print(f"\r  마우스 좌표  x={int(x):5d}  y={int(y):5d}    ", end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


# --- test ----------------------------------------------------------------


def _first_match(
    image: Path, haystack: Any, region: tuple[int, int, int, int] | None
) -> tuple[float | None, matcher.Box | None]:
    """임계값을 0.95부터 0.70까지 낮추며 처음 잡히는 값을 찾는다."""
    for confidence in CONFIDENCE_STEPS:
        box = matcher.locate(image, haystack, confidence, region)
        if box is not None:
            return confidence, box
    return None, None


def cmd_test(args: argparse.Namespace) -> int:
    profile = config.load(args.config, args.profile)
    scale = matcher.detect_scale()
    size = pg().size()
    screen = (int(size[0]), int(size[1]))
    region = matcher.to_physical_region(profile.region, scale)

    log(f"프로파일 '{profile.name}' 이미지 검사 — 클릭하지 않습니다")
    log(f"화면: 논리 {screen[0]}x{screen[1]}, 배율 {scale:g}x, 설정 임계값 {profile.confidence:g}")
    log(f"감시 영역: {'전체 화면' if profile.region is None else str(list(profile.region))}")
    print()

    haystack = matcher.grab()
    matched = 0

    for target in profile.targets:
        try:
            confidence, box = _first_match(target.image, haystack, region)
        except Exception as exc:
            # 이미지 하나가 깨져도 나머지 대상은 계속 검사한다.
            print(f"❌ '{target.name}'  {target.image}")
            print(f"     검사 실패 — {exc!r}")
            print("     이미지가 감시 영역보다 크거나 파일이 손상됐을 수 있습니다.\n")
            continue

        if confidence is None or box is None:
            print(f"❌ '{target.name}'  {target.image}")
            print("     0.95~0.70 어느 임계값에서도 찾지 못했습니다.")
            print("     대상 창이 지금 화면에 실제로 보이는지, 이미지를 다시 캡처할지 확인하세요.\n")
            continue

        matched += 1
        center = matcher.logical_center(box, scale)
        x, y = clicker.resolve_click(target.click, center)
        print(f"✅ '{target.name}'  {target.image}")
        print(f"     최초 매칭 임계값 {confidence:.2f}")
        if profile.confidence <= confidence:
            print(f"     설정값 {profile.confidence:g} → 현재 설정으로 잡힙니다")
        else:
            print(
                f"     설정값 {profile.confidence:g} 로는 못 잡습니다 → "
                f"confidence 를 {max(0.1, round(confidence - 0.05, 2)):g} 근처로 낮추세요"
            )
        print(f"     이미지 중앙 x={center[0]} y={center[1]} → 클릭 지점 x={x} y={y} [{target.click.mode}]")

        # 후보가 여러 곳이면 '가장 위·왼쪽'이 선택된다. 원하는 위치가 아닐 수 있다.
        hits = matcher.count_matches(
            target.image, haystack, confidence, region, limit=AMBIGUITY_LIMIT
        )
        if hits > 1:
            amount = f"{AMBIGUITY_LIMIT}곳 이상" if hits >= AMBIGUITY_LIMIT else f"{hits}곳"
            print(f"     ⚠️  임계값 {confidence:.2f}에서 {amount}이 매칭됩니다 (가장 위·왼쪽이 선택됨)")
            print("         특징이 뚜렷한 부분으로 다시 자르거나, 임계값을 올리거나, region 으로 좁히세요")

        if not clicker.in_bounds(x, y, screen):
            print(f"     ⚠️  클릭 지점이 화면 {screen[0]}x{screen[1]} 밖입니다. 실행해도 건너뜁니다")
        print()

    total = len(profile.targets)
    log(f"검사 결과: {matched}/{total} 매칭")
    return 0 if matched == total else 1


# --- doctor / init -------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    config_path = config.resolve_config_path(args.config)
    marks = {True: "✅", False: "❌", None: "⚠️ "}
    results = doctor.run_checks(config_path, args.profile)

    print("=== itc doctor — 실행 전 환경 점검 ===\n")
    for check in results:
        # 여러 줄짜리 안내도 항목 아래에 나란히 붙도록 들여쓴다.
        detail = check.detail.replace("\n", "\n   ")
        print(f"{marks[check.ok]} {check.title}: {detail}")
        if check.fix and check.ok is not True:
            print("   → " + check.fix.replace("\n", "\n     "))
        print()

    failed = sum(1 for c in results if c.ok is False)
    unknown = sum(1 for c in results if c.ok is None)
    if failed:
        print(f"문제 {failed}건. 위 안내대로 고친 뒤 다시 실행하세요.")
        return 1
    note = f" (확인 필요 {unknown}건)" if unknown else ""
    print(f"문제 없음{note}. `itc run --dry-run` 으로 검증해 보세요.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    config_path = config.resolve_config_path(args.config)
    image_dir = config_path.parent / "images"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(exist_ok=True)

    if config_path.exists() and not args.force:
        print(f"설정 파일이 이미 있습니다: {config_path}")
        print("덮어쓰려면 --force 를 붙이세요.")
        return 1

    config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    print(f"설정 파일 생성: {config_path}")
    print(f"이미지 디렉터리: {image_dir}")
    print()
    print("다음 순서로 진행하세요:")
    print("  1. itc doctor                     권한·환경 점검")
    print("  2. itc pos                        클릭할 지점의 좌표 확인")
    print(f"  3. Cmd+Shift+4 로 트리거 이미지를 캡처해 {image_dir} 에 저장")
    print(f"  4. {config_path} 편집")
    print("  5. itc test                       임계값 확인")
    print("  6. itc run --dry-run              클릭 없이 동작 검증")
    print("  7. itc run                        실행")
    return 0


# --- 파서 ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="itc",
        description="화면 이미지를 트리거로 지정한 좌표를 클릭하는 범용 데스크톱 자동화 도구",
    )
    parser.add_argument("--version", action="version", version=f"image-trigger-clicker {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser, *, profile: bool = True) -> None:
        sub.add_argument(
            "--config",
            metavar="PATH",
            help=f"설정 파일 경로 (기본: {config.DEFAULT_CONFIG_PATH})",
        )
        if profile:
            sub.add_argument("--profile", metavar="이름", help="사용할 프로파일 이름")

    run_parser = subparsers.add_parser("run", help="감시 루프 실행")
    add_common(run_parser)
    run_parser.add_argument(
        "--dry-run", action="store_true", help="매칭 로그만 남기고 실제 클릭은 하지 않는다"
    )
    run_parser.add_argument("--log-file", metavar="PATH", help="로그를 파일에도 기록")
    run_parser.set_defaults(func=cmd_run)

    pos_parser = subparsers.add_parser("pos", help="마우스 좌표를 실시간 표시 (Ctrl+C 종료)")
    pos_parser.set_defaults(func=cmd_pos)

    test_parser = subparsers.add_parser("test", help="현재 화면에서 이미지가 잡히는지 1회 검사")
    add_common(test_parser)
    test_parser.set_defaults(func=cmd_test)

    doctor_parser = subparsers.add_parser("doctor", help="권한·환경 점검")
    add_common(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    init_parser = subparsers.add_parser("init", help="설정 디렉터리와 샘플 설정 생성")
    add_common(init_parser, profile=False)
    init_parser.add_argument("--force", action="store_true", help="기존 설정 파일을 덮어쓴다")
    init_parser.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except config.ConfigError as exc:
        error(str(exc))
        return 2
    except KeyboardInterrupt:
        print()
        return 130
    finally:
        close_log_file()
