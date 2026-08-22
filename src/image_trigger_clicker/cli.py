"""명령줄 진입점. `itc <서브커맨드>`."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

from . import __version__, clicker, config, doctor, matcher, recorder
from .logging import close_log_file, error, log, open_log_file, warn

__all__ = ["main"]

# 이 아래로는 "사실상 못 찾은 것"으로 본다.
MATCH_FLOOR = 0.70

# 후보가 여러 곳일 때 몇 곳까지 세어 볼지.
CANDIDATE_LIMIT = 20

HEARTBEAT_EVERY = 60  # 검사 몇 회마다 생존 확인 로그를 남길지

# itc record 가 클릭 주변을 잘라낼 기본 크기 (논리 좌표 너비x높이).
DEFAULT_CROP = (160, 48)

SAMPLE_CONFIG = '''# image-trigger-clicker 설정 파일
#
# 화면에 지정한 이미지가 나타나면, 미리 정해둔 좌표를 클릭한다.
# 핵심: 이미지는 "언제 누를지"를 판단하는 트리거일 뿐이다.
#       "어디를 누를지"는 아래 click 에서 따로 정한다.
#
# 좌표는 전부 논리 좌표(= `itc pos` 가 보여주는 값)로 적는다.
#
# 트리거 이미지는 손으로 만들지 말고 다음 둘 중 하나를 쓰는 게 빠르다.
#   itc capture <이름>   영역을 드래그해서 바로 저장 + 모호성 검사
#   itc record           클릭을 녹화해서 설정 초안을 통째로 생성

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


# --- 공용 헬퍼 ------------------------------------------------------------


def _screen_lines(screen: matcher.Screen) -> list[str]:
    """화면 구성을 사람이 읽을 수 있게. 모니터가 여러 대면 각각도 보여준다."""
    physical = f"{round(screen.width * screen.scale)}x{round(screen.height * screen.scale)}"
    origin = "" if (screen.left, screen.top) == (0, 0) else f" 원점({screen.left},{screen.top})"
    label = "화면" if len(screen.displays) <= 1 else "화면(가상 데스크톱)"
    lines = [
        f"{label}: 논리 {screen.width}x{screen.height}{origin} / "
        f"물리 {physical}, 배율 {screen.scale:g}x"
    ]
    if len(screen.displays) > 1:
        for i, d in enumerate(screen.displays, 1):
            main = " (주 디스플레이)" if d.is_main else ""
            lines.append(
                f"  모니터 {i}: 원점({d.left},{d.top}) {d.width}x{d.height} 배율 {d.scale:g}x{main}"
            )
        if screen.mixed_scales:
            lines.append(
                "  [경고] 모니터마다 배율이 다릅니다. 단일 배율로 환산하므로 "
                "주 디스플레이가 아닌 곳에서는 좌표가 어긋날 수 있습니다"
            )
    return lines


def _safe_filename(name: str) -> str:
    """대상 이름을 파일명으로 쓸 수 있게 다듬는다 (한글은 그대로 둔다)."""
    cleaned = re.sub(r'[/\\:*?"<>|\x00-\x1f]', "_", name).strip().strip(".")
    return cleaned or "target"


def _match_center(match: matcher.Match, screen: matcher.Screen) -> tuple[int, int]:
    return screen.to_logical(match.left + match.width / 2, match.top + match.height / 2)


def _candidate_note(count: int) -> list[str]:
    """후보가 여러 곳일 때의 경고 문구. 1곳이면 빈 목록."""
    if count <= 1:
        return []
    amount = f"{CANDIDATE_LIMIT}곳 이상" if count >= CANDIDATE_LIMIT else f"{count}곳"
    return [
        f"⚠️  같은 임계값에서 {amount}이 매칭됩니다 (가장 닮은 곳을 고르지만 순위가 뒤집힐 수 있음)",
        "    특징이 뚜렷한 부분으로 다시 자르거나, 임계값을 올리거나, region 으로 좁히세요",
    ]


def _target_snippet(profile_name: str, name: str, image_rel: str, click_line: str) -> str:
    return (
        f"[[profiles.{profile_name}.targets]]\n"
        f'name     = "{name}"\n'
        f'image    = "{image_rel}"\n'
        f"click    = {click_line}\n"
        f"cooldown = 5.0\n"
    )


# --- run ------------------------------------------------------------------


def _log_startup(
    profile: config.Profile,
    screen: matcher.Screen,
    dry_run: bool,
    record_dir: Path | None,
) -> None:
    suffix = " (DRY-RUN: 클릭하지 않습니다)" if dry_run else ""
    log(f"image-trigger-clicker {__version__} 시작{suffix}")
    for line in _screen_lines(screen):
        log(line)
    log(
        f"프로파일 '{profile.name}' — 주기 {profile.interval:g}초, "
        f"임계값 {profile.confidence:g}, 클릭 지연 {profile.click_delay:g}초"
    )
    log(f"감시 영역: {'전체 화면' if profile.region is None else str(list(profile.region))}")
    if record_dir is not None:
        log(f"실행 녹화: 클릭할 때마다 {record_dir} 에 스크린샷 저장")
    log(f"감시 대상 {len(profile.targets)}개:")
    for i, target in enumerate(profile.targets, 1):
        log(
            f"  {i}. '{target.name}' ← {target.image.name} | "
            f"클릭 {target.click.describe()} | 쿨다운 {target.cooldown:g}초"
        )
    log("긴급 정지: 마우스를 화면 왼쪽 위 모서리로 (FailSafe) 또는 Ctrl+C")


def _save_record(
    record_dir: Path, frame: Any, screen: matcher.Screen, x: int, y: int, name: str
) -> None:
    """클릭 순간을 표시한 스크린샷을 남긴다. 실패해도 루프는 계속된다."""
    try:
        record_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = record_dir / f"{stamp}_{_safe_filename(name)}.png"
        recorder.annotate(frame, screen, x, y, f"{name} ({x},{y})").save(path, compress_level=1)
    except Exception as exc:
        warn(f"실행 녹화 저장 실패(계속 진행) — {exc!r}")


def _scan_once(
    profile: config.Profile,
    region: tuple[int, int, int, int] | None,
    screen: matcher.Screen,
    last_click: dict[str, float],
    out_of_bounds: set[str],
    dry_run: bool,
    record_dir: Path | None,
) -> int:
    """화면을 한 번 찍어 모든 대상을 검사한다. 이번에 클릭한 횟수를 돌려준다."""
    haystack = matcher.grab()
    performed = 0

    for target in profile.targets:
        since = time.monotonic() - last_click.get(target.name, float("-inf"))
        if since < target.cooldown:
            continue

        match = matcher.locate(target.image, haystack, profile.confidence, region)
        if match is None:
            continue

        center = _match_center(match, screen)
        x, y = clicker.resolve_click(target.click, center)

        # 계산된 좌표가 화면 밖이면 절대 누르지 않는다.
        # 매 주기 같은 경고를 쏟아내면 장시간 로그가 못 쓰게 되므로, 범위 밖으로
        # "들어간 순간"에만 남기고 다시 안으로 들어오면 상태를 푼다.
        if not clicker.in_bounds(x, y, screen):
            if target.name not in out_of_bounds:
                out_of_bounds.add(target.name)
                warn(
                    f"'{target.name}' 클릭 지점 x={x} y={y} 이(가) 화면 범위 "
                    f"({screen.left},{screen.top})~({screen.right},{screen.bottom}) 밖입니다. "
                    "클릭하지 않고 건너뜁니다 (같은 경고는 범위 안으로 돌아올 때까지 생략)"
                )
            continue
        out_of_bounds.discard(target.name)

        log(
            f"매칭: '{target.name}' 유사도 {match.score:.3f}, 중앙 x={center[0]} y={center[1]} → "
            f"{profile.click_delay:g}초 후 {target.click.describe()}"
        )
        if record_dir is not None:
            _save_record(record_dir, haystack, screen, x, y, target.name)
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
    record_dir = Path(args.record_dir).expanduser() if args.record_dir else None

    screen = matcher.detect_screen()
    region = screen.to_physical_region(profile.region)
    _log_startup(profile, screen, args.dry_run, record_dir)

    checks = 0
    clicks = 0
    last_click: dict[str, float] = {}
    out_of_bounds: set[str] = set()

    try:
        while True:
            checks += 1
            try:
                clicks += _scan_once(
                    profile, region, screen, last_click, out_of_bounds, args.dry_run, record_dir
                )
            except pg_failsafe():
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
    except pg_failsafe():
        log("긴급 정지(FailSafe): 마우스가 화면 모서리에 닿아 중단합니다")
    finally:
        log(f"정리 완료 — 총 검사 {checks}회, 클릭 {clicks}회")
        close_log_file()
    return 0


def pg_failsafe() -> type[BaseException]:
    """pyautogui.FailSafeException. 지연 임포트라 함수로 감싼다."""
    from . import pg

    exc: type[BaseException] = pg().FailSafeException
    return exc


# --- pos ------------------------------------------------------------------


def cmd_pos(_args: argparse.Namespace) -> int:
    from . import pg

    screen = matcher.detect_screen()
    for line in _screen_lines(screen):
        print(line)
    print("클릭할 지점에 마우스를 올려두고 값을 읽으세요. Ctrl+C 로 종료합니다.\n")
    try:
        while True:
            x, y = pg().position()
            print(f"\r  마우스 좌표  x={int(x):5d}  y={int(y):5d}    ", end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


# --- test -----------------------------------------------------------------


def cmd_test(args: argparse.Namespace) -> int:
    profile = config.load(args.config, args.profile)
    screen = matcher.detect_screen()
    region = screen.to_physical_region(profile.region)

    log(f"프로파일 '{profile.name}' 이미지 검사 — 클릭하지 않습니다")
    for line in _screen_lines(screen):
        log(line)
    log(f"설정 임계값 {profile.confidence:g}")
    log(f"감시 영역: {'전체 화면' if profile.region is None else str(list(profile.region))}")
    print()

    haystack = matcher.grab()
    matched = 0

    for target in profile.targets:
        try:
            # 임계값 0으로 불러 '실제 유사도'를 그대로 받는다.
            best = matcher.locate(target.image, haystack, 0.0, region)
        except Exception as exc:
            print(f"❌ '{target.name}'  {target.image}")
            print(f"     검사 실패 — {exc}")
            print()
            continue

        if best is None or best.score < MATCH_FLOOR:
            score = 0.0 if best is None else best.score
            print(f"❌ '{target.name}'  {target.image}")
            print(f"     유사도 {score:.3f} — {MATCH_FLOOR:g} 미만이라 사실상 못 찾은 것입니다.")
            print("     대상 창이 지금 화면에 실제로 보이는지, 이미지를 다시 캡처할지 확인하세요.")
            print()
            continue

        matched += 1
        center = _match_center(best, screen)
        x, y = clicker.resolve_click(target.click, center)
        print(f"✅ '{target.name}'  {target.image}")
        if profile.confidence <= best.score:
            print(f"     유사도 {best.score:.3f}  (설정값 {profile.confidence:g} → 현재 설정으로 잡힙니다)")
        else:
            suggested = max(MATCH_FLOOR, round(best.score - 0.05, 2))
            print(
                f"     유사도 {best.score:.3f}  (설정값 {profile.confidence:g} 로는 못 잡습니다 → "
                f"confidence 를 {suggested:g} 근처로 낮추세요)"
            )
        print(f"     이미지 중앙 x={center[0]} y={center[1]} → 클릭 지점 x={x} y={y} [{target.click.mode}]")

        count = matcher.count_candidates(
            target.image, haystack, profile.confidence, region, CANDIDATE_LIMIT
        )
        for line in _candidate_note(count):
            print(f"     {line}")
        if not clicker.in_bounds(x, y, screen):
            print("     ⚠️  클릭 지점이 화면 범위 밖입니다. 실행해도 건너뜁니다")
        print()

    total = len(profile.targets)
    log(f"검사 결과: {matched}/{total} 매칭")
    return 0 if matched == total else 1


# --- capture --------------------------------------------------------------


def cmd_capture(args: argparse.Namespace) -> int:
    config_path = config.resolve_config_path(args.config)
    images_dir = config_path.parent / "images"
    dest = images_dir / f"{_safe_filename(args.name)}.png"

    if dest.exists() and not args.force:
        print(f"이미 있습니다: {dest}")
        print("덮어쓰려면 --force 를 붙이세요.")
        return 1

    print("트리거로 쓸 영역을 드래그해서 선택하세요. (Esc = 취소)")
    print("  항상 똑같이 보이는 부분만 — 바뀌는 텍스트나 밋밋한 배경은 피하세요.\n")
    if not recorder.capture_region(dest):
        print("취소했습니다. 저장된 것이 없습니다.")
        return 1

    from PIL import Image

    with Image.open(dest) as img:
        size = img.size
    print(f"저장: {dest}  ({size[0]}x{size[1]} 물리 픽셀)\n")

    screen = matcher.detect_screen()
    haystack = matcher.grab()
    try:
        best = matcher.locate(dest, haystack, 0.0)
        count = matcher.count_candidates(dest, haystack, args.confidence, None, CANDIDATE_LIMIT)
    except Exception as exc:
        print(f"검사 실패 — {exc}")
        return 1

    if best is None or best.score < MATCH_FLOOR:
        print("⚠️  방금 저장한 이미지를 현재 화면에서 다시 찾지 못했습니다.")
        print("    선택 직후 화면이 바뀌었을 수 있습니다(메뉴가 닫혔다든지).")
    else:
        center = _match_center(best, screen)
        print(f"현재 화면에서 유사도 {best.score:.3f}, 중앙 x={center[0]} y={center[1]}")
        for line in _candidate_note(count):
            print(f"  {line}")
        if count == 1:
            print(f"  후보 1곳 — 임계값 {args.confidence:g}에서 유일합니다. 좋은 트리거입니다.")

    profile_name = args.profile or "sample"
    print("\n설정에 붙여넣으세요:\n")
    print(
        _target_snippet(
            profile_name, args.name, f"images/{dest.name}", '{ mode = "center" }'
        )
    )
    print("클릭 지점이 이미지 중앙이 아니면 click 을 offset 이나 abs 로 바꾸세요.")
    print("(`itc pos` 로 좌표 확인, 자세한 내용은 README)")
    return 0


# --- record ---------------------------------------------------------------


def _parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"크기는 '너비x높이' 형식이어야 합니다 (받은 값: {text!r})")
    return int(m.group(1)), int(m.group(2))


def cmd_record(args: argparse.Namespace) -> int:
    config_path = config.resolve_config_path(args.config)
    images_dir = config_path.parent / "images"
    frames_dir = config_path.parent / "frames"
    images_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    screen = matcher.detect_screen()
    prefix = _safe_filename(args.name)
    profile_name = args.profile or "recorded"
    recorded: list[dict[str, Any]] = []

    for line in _screen_lines(screen):
        log(line)
    log(f"클릭 녹화 시작 — 클릭 주변 {args.size[0]}x{args.size[1]} (논리)를 트리거로 잘라냅니다")
    log("대상 창에서 평소처럼 클릭하세요. 클릭은 그대로 전달됩니다.")
    log("끝나면 Ctrl+C — 그때 이미지와 설정 초안을 씁니다.")
    print()

    def on_click(event: recorder.ClickEvent) -> None:
        index = len(recorded) + 1
        stem = f"{prefix}-{index}"
        crop = recorder.crop_around(event.frame, screen, event.x, event.y, args.size)
        crop_path = images_dir / f"{stem}.png"
        frame_path = frames_dir / f"{stem}.png"
        crop.save(crop_path)
        event.frame.save(frame_path, compress_level=1)
        recorded.append({"stem": stem, "x": event.x, "y": event.y, "crop": crop_path})
        log(f"기록 {index}: x={event.x} y={event.y} → {crop_path.name} ({crop.width}x{crop.height})")

    try:
        recorder.record_clicks(screen, on_click)
    except KeyboardInterrupt:
        print()
    except RuntimeError as exc:
        error(str(exc))
        return 2

    if not recorded:
        log("기록된 클릭이 없습니다. 아무것도 쓰지 않았습니다.")
        return 1

    # 잘라낸 트리거가 화면에서 유일한지 확인해준다.
    log(f"클릭 {len(recorded)}건 기록 — 트리거 유일성 검사 중")
    haystack = matcher.grab()
    for item in recorded:
        try:
            count = matcher.count_candidates(
                item["crop"], haystack, args.confidence, None, CANDIDATE_LIMIT
            )
        except Exception:
            count = 0
        item["candidates"] = count
        if count > 1:
            warn(f"'{item['stem']}' 는 지금 화면에서 {count}곳과 닮았습니다 — 다시 자르는 게 좋습니다")

    draft = config_path.parent / "config.recorded.toml"
    lines = [
        "# itc record 가 만든 초안입니다. 확인한 뒤 config.toml 로 옮기세요.",
        "# 트리거 이미지는 클릭 지점 주위를 잘라낸 것이라 click 은 center 입니다.",
        "# 화면 곳곳에서 매칭되는 항목은 `itc capture <이름>` 으로 더 특징적인 부분을",
        "# 다시 잘라 바꾸세요. 원본 전체 화면은 frames/ 에 남아 있습니다.",
        "",
        f"[profiles.{profile_name}]",
        "interval    = 2.0",
        f"confidence  = {args.confidence:g}",
        "click_delay = 0.3",
        "",
    ]
    for item in recorded:
        note = "" if item["candidates"] <= 1 else f"   # 주의: 후보 {item['candidates']}곳"
        lines.append(f"[[profiles.{profile_name}.targets]]{note}")
        lines.append(f'name     = "{item["stem"]}"')
        lines.append(f'image    = "images/{item["stem"]}.png"')
        lines.append('click    = { mode = "center" }')
        lines.append("cooldown = 5.0")
        lines.append("")
    draft.write_text("\n".join(lines), encoding="utf-8")

    log(f"설정 초안: {draft}")
    log(f"트리거 이미지: {images_dir}")
    log(f"원본 전체 화면: {frames_dir}")
    print()
    print("다음 순서로 확인하세요:")
    print(f"  1. {draft} 를 열어 이름과 click 방식을 다듬기")
    print("  2. config.toml 로 옮기기")
    print(f"  3. itc test --profile {profile_name}")
    print(f"  4. itc run --dry-run --profile {profile_name}")
    return 0


# --- doctor / init --------------------------------------------------------


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
    print("  2. itc record                     클릭을 녹화해 설정 초안 생성 (가장 빠름)")
    print("     또는 itc capture <이름>        영역을 드래그해 트리거 이미지 저장")
    print("  3. itc test                       유사도·후보 수 확인")
    print("  4. itc run --dry-run              클릭 없이 동작 검증")
    print("  5. itc run                        실행")
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
    run_parser.add_argument(
        "--record-dir",
        metavar="DIR",
        help="클릭할 때마다 그 순간 화면을 표시해서 저장 (무인 실행 사후 검증용)",
    )
    run_parser.set_defaults(func=cmd_run)

    pos_parser = subparsers.add_parser("pos", help="마우스 좌표를 실시간 표시 (Ctrl+C 종료)")
    pos_parser.set_defaults(func=cmd_pos)

    test_parser = subparsers.add_parser("test", help="현재 화면에서 이미지가 잡히는지 1회 검사")
    add_common(test_parser)
    test_parser.set_defaults(func=cmd_test)

    capture_parser = subparsers.add_parser(
        "capture", help="영역을 드래그해 트리거 이미지 저장 + 모호성 검사"
    )
    capture_parser.add_argument("name", help="대상 이름 (파일명과 설정의 name 으로 쓰임)")
    add_common(capture_parser)
    capture_parser.add_argument(
        "--confidence", type=float, default=0.9, help="모호성 검사에 쓸 임계값 (기본 0.9)"
    )
    capture_parser.add_argument("--force", action="store_true", help="같은 이름 파일을 덮어쓴다")
    capture_parser.set_defaults(func=cmd_capture)

    record_parser = subparsers.add_parser(
        "record", help="클릭을 녹화해 트리거 이미지와 설정 초안을 생성"
    )
    add_common(record_parser)
    record_parser.add_argument("--name", default="recorded", help="파일 이름 접두어 (기본 recorded)")
    record_parser.add_argument(
        "--size",
        type=_parse_size,
        default=DEFAULT_CROP,
        metavar="너비x높이",
        help=f"클릭 주변을 잘라낼 크기, 논리 좌표 (기본 {DEFAULT_CROP[0]}x{DEFAULT_CROP[1]})",
    )
    record_parser.add_argument(
        "--confidence", type=float, default=0.85, help="초안에 넣을 임계값 (기본 0.85)"
    )
    record_parser.set_defaults(func=cmd_record)

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
