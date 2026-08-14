# homebrew-tap 저장소 준비

이 디렉터리의 내용은 **별도 저장소**에 들어간다. 메인 저장소(`image-trigger-clicker`)에
같이 두면 `brew tap` 이 동작하지 않는다.

현재 반영된 tap: <https://github.com/yuangunn/homebrew-tap>

## 1. tap 저장소 만들기

저장소 이름은 **반드시 `homebrew-tap`** 이어야 한다. Homebrew 가
`brew tap <계정>/tap` → `github.com/<계정>/homebrew-tap` 으로 해석하기 때문이다.
이름이 `homebrew-` 로 시작하지 않으면 tap 으로 인식되지 않는다.

```bash
gh repo create yuangunn/homebrew-tap --public --clone
cd homebrew-tap
mkdir -p Formula
cp ../image-trigger-clicker/packaging/homebrew-tap/Formula/image-trigger-clicker.rb Formula/
git add . && git commit -m "Add image-trigger-clicker formula" && git push
```

## 2. 설치 검증

```bash
brew tap yuangunn/tap
brew install image-trigger-clicker
itc doctor
```

`brew install` 이 끝나면 **반드시 `itc doctor`** 로 권한 상태를 확인한다.
화면 기록 권한이 없으면 스크린샷이 검은 화면으로 나오고, 오류 없이 조용히
아무것도 매칭되지 않는다.

formula 자체 검증:

```bash
brew install --build-from-source yuangunn/tap/image-trigger-clicker
brew test image-trigger-clicker
brew audit --strict --online yuangunn/tap/image-trigger-clicker
```

## 3. 의존성: 무엇을 휠로, 무엇을 sdist 로

`virtualenv_install_with_resources` 는 모든 resource 를 sdist 에서 빌드한다
(`pip --no-binary=:all:`). 그런데 셋은 그 방식으로 설치되지 않는다.

| 패키지 | sdist 빌드가 안 되는 이유 |
|---|---|
| `numpy` | Apple clang 으로 컴파일이 깨진다. Homebrew 의 numpy formula 도 `depends_on "gcc" => :build` 로 gcc 를 쓴다 |
| `opencv-python` | CMake 로 OpenCV 전체를 빌드한다(30~60분, 자주 실패). 게다가 그 빌드 의존성이 numpy 라 위 문제를 먼저 만난다 |
| `pillow` | jpeg/tiff/webp 등 이미지 라이브러리 헤더를 요구한다 |

실제로 v0.1.0 을 전부 sdist 로 설치해 보다가 **11분 만에 numpy 컴파일 오류**
(`string_fastsearch.h` 템플릿 치환 실패)로 깨졌다.

그래서 이 셋만 공식 배포 **휠**을 그대로 설치한다. 나머지(pyautogui 계열, pyobjc)는
sdist 그대로 두며 1분 안에 빌드된다.

### 휠을 pip 에 넘길 때 주의

Homebrew 는 내려받은 파일을 캐시에 `<sha256>--원래이름` 으로 저장한다.
그 경로를 그대로 pip 에 주면 이렇게 거부당한다.

```
ERROR: Invalid wheel filename (wrong number of parts): 'f22add...--opencv_python-5.0.0.93-cp37-abi3-macosx_13_0_arm64'
```

그래서 formula 의 `install` 에서 원래 파일명으로 복사한 뒤 넘긴다.
`pip` 는 `--no-binary=:all:` 이 켜져 있어도 **명시적으로 준 로컬 `.whl` 파일**은
그대로 설치한다(확인함).

### 휠 갱신

휠은 파이썬 버전·아키텍처마다 다르다. formula 는 `python@3.12` 를 고정하고
`on_arm` / `on_intel` 블록으로 나눠 둔다. 버전을 올릴 때는 PyPI 에서 다음 조건에
맞는 휠 URL 과 sha256 을 가져온다.

- `numpy`, `pillow` → `cp312` + `macosx_*_arm64` / `macosx_*_x86_64`
- `opencv-python` → `cp37-abi3` + `macosx_*_arm64` / `macosx_*_x86_64`

```bash
python3 - <<'PY'
import json, urllib.request
for pkg, ver in [("numpy","2.5.2"), ("opencv-python","5.0.0.93"), ("pillow","12.3.0")]:
    d = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/{ver}/json"))
    for u in d["urls"]:
        fn = u["filename"]
        if u["packagetype"] == "bdist_wheel" and "macosx" in fn and ("cp312" in fn or "abi3" in fn):
            print(fn, u["url"], u["digests"]["sha256"], sep="\n  ")
PY
```

## 4. sdist resource 스탠자 갱신

나머지 의존성은 손으로 쓰지 말고 Homebrew 가 생성하게 한다.

```bash
brew update-python-resources image-trigger-clicker
```

`pyproject.toml` 의 `dependencies` 를 읽어 의존성 트리 전체를 풀고, 각 패키지의
sdist URL 과 SHA256 을 formula 에 써넣는다.

**주의**: 이 명령은 `numpy` / `opencv-python` / `pillow` 도 sdist 스탠자로 덮어쓴다.
실행한 뒤에는 그 셋을 위 휠 형태(`on_arm` / `on_intel` 블록)로 되돌려야 한다.

## 5. 검토했지만 쓰지 않은 대안: `depends_on "opencv"`

Homebrew 가 미리 빌드해 둔 bottle 을 쓰는 방법이다. 빠르고 안정적이지만
**brew 의 opencv 5.0 은 의존 formula 를 106개 끌고 온다** — Qt, VTK, OpenVINO,
ffmpeg, tesseract, boost, hdf5, gcc 까지. 수 GB다.
`cv2.matchTemplate` 하나 때문에 치르기엔 과한 비용이라 쓰지 않았다.
(참고로 휠 방식의 Cellar 용량은 183MB.)

그래도 순정 Homebrew 구성을 원한다면:

1. formula 에서 `on_arm` / `on_intel` 의 휠 resource 블록을 지운다.
2. `depends_on` 을 바꾼다. **brew 의 opencv 는 `python@3.14` 용으로 빌드되므로
   formula 의 파이썬도 3.14 로 맞춰야 한다.**

   ```ruby
   depends_on "numpy"
   depends_on "opencv"
   depends_on "pillow"
   depends_on "python@3.14"
   ```

3. `install` 에서 brew 의 site-packages 를 venv 에 노출한다.

   ```ruby
   def install
     virtualenv_install_with_resources
     site = Language::Python.site_packages("python3.14")
     (libexec/site/"homebrew-deps.pth").write <<~PTH
       #{Formula["opencv"].opt_lib}/#{site}
       #{Formula["numpy"].opt_lib}/#{site}
       #{Formula["pillow"].opt_lib}/#{site}
     PTH
   end
   ```

**트레이드오프**: 설치 용량이 수 GB로 늘고 brew 의 opencv 업그레이드에 영향을 받는다.
대신 모든 바이너리를 Homebrew 가 직접 빌드한 것으로 통일할 수 있다.

## 6. 릴리스 자동 갱신 설정

메인 저장소의 `.github/workflows/update-tap.yml` 이 **태그 푸시** 시 formula 의
`url` / `sha256` 을 자동 커밋한다. 다음 시크릿이 필요하다.

| 시크릿 | 값 |
|---|---|
| `TAP_GITHUB_TOKEN` | `homebrew-tap` 저장소에 `contents: write` 권한이 있는 PAT |

기본 `GITHUB_TOKEN` 은 다른 저장소에 쓸 수 없으므로 별도 토큰이 반드시 필요하다.
Fine-grained personal access token 으로 `homebrew-tap` 저장소만 대상으로 발급하는 것을 권장한다.

```bash
gh secret set TAP_GITHUB_TOKEN --repo yuangunn/image-trigger-clicker
```

`release: published` 가 아니라 태그 푸시에 거는 이유는 `update-tap.yml` 상단 주석 참고.

## 서명·공증

하지 않는다. `itc` 는 `.app` 번들이 아니라 Homebrew 로 설치되는 CLI 실행 파일이라
Gatekeeper 격리 검사 대상이 아니다. 자세한 내용은 메인 README 의
"코드 서명·공증에 대하여" 절을 보라.
