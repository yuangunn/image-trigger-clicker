# homebrew-tap 저장소 준비

이 디렉터리의 내용은 **별도 저장소**에 들어간다. 메인 저장소(`image-trigger-clicker`)에
같이 두면 `brew tap` 이 동작하지 않는다.

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

## 2. url 과 sha256 채우기

formula 최상단의 `url` / `sha256` 은 첫 릴리스 전까지 자리표시자다.
첫 릴리스 태그를 민 뒤 직접 채우거나, `update-tap.yml` 워크플로를 수동 실행한다.

```bash
TAG=v0.1.0
URL="https://github.com/yuangunn/image-trigger-clicker/archive/refs/tags/${TAG}.tar.gz"
curl -fsSL "$URL" -o source.tar.gz
shasum -a 256 source.tar.gz
```

이후 릴리스부터는 메인 저장소의 `update-tap.yml` 이 자동으로 갱신한다.

## 3. resource 스탠자 생성 / 갱신

Python 의존성은 formula 안에 `resource` 스탠자로 고정해야 한다. 손으로 쓰지 말고
Homebrew 가 생성하게 한다.

```bash
brew tap yuangunn/tap
brew update-python-resources image-trigger-clicker
```

이 명령은 `pyproject.toml` 의 `dependencies` 를 읽어 의존성 트리 전체를 풀고,
각 패키지의 sdist URL 과 SHA256 을 formula 에 써넣는다.
(formula 안에 이미 있는 `resource` 블록은 통째로 교체된다.)

의존성 버전을 올린 뒤에는 반드시 다시 실행한다.

### `brew update-python-resources` 가 opencv-python 에서 실패하면

`opencv-python` 은 sdist 를 받으면 CMake 로 OpenCV 전체를 컴파일한다.
용량이 크고 30분 이상 걸리며, 툴체인 문제로 실패하는 일도 잦다.
`brew update-python-resources` 자체가 이 패키지에서 멈추기도 한다.

그럴 때는 **Homebrew 가 이미 빌드해 둔 opencv 를 쓴다.**

1. formula 에서 `resource "opencv-python"` 과 `resource "numpy"` 블록을 지운다.
2. `depends_on` 을 추가한다.

   ```ruby
   depends_on "numpy"
   depends_on "opencv"
   ```

3. `install` 을 바꿔서 brew 의 `cv2` / `numpy` 를 venv 에서 볼 수 있게 한다.

   ```ruby
   def install
     virtualenv_install_with_resources
     site = Language::Python.site_packages("python3.12")
     (libexec/site/"homebrew-deps.pth").write <<~PTH
       #{Formula["opencv"].opt_lib}/#{site}
       #{Formula["numpy"].opt_lib}/#{site}
     PTH
   end
   ```

4. resource 를 다시 생성할 때는 opencv-python 을 제외해야 하므로,
   `brew update-python-resources` 실행 뒤 생성된 `opencv-python` / `numpy`
   블록을 다시 지운다.

같은 내용이 formula 파일 상단 주석에도 있다.

**트레이드오프**: 설치는 훨씬 빠르고 안정적이지만, brew 의 `opencv` 가 업그레이드되면
이 도구도 함께 영향을 받는다. resource 방식은 버전이 formula 에 고정되어 재현성이 높다.

## 4. 설치 검증

```bash
brew tap yuangunn/tap
brew install image-trigger-clicker
itc doctor
```

`brew install` 이 끝나면 **반드시 `itc doctor`** 로 권한 상태를 확인한다.
화면 기록 권한이 없으면 스크린샷이 검은 화면으로 나오고, 오류 없이 조용히
아무것도 매칭되지 않는다.

formula 자체를 검증하려면:

```bash
brew audit --strict --online yuangunn/tap/image-trigger-clicker
brew test image-trigger-clicker
brew install --build-from-source yuangunn/tap/image-trigger-clicker
```

## 5. 릴리스 자동 갱신 설정

메인 저장소의 `.github/workflows/update-tap.yml` 이 릴리스 게시 후 formula 를
자동으로 커밋한다. 다음 시크릿이 필요하다.

| 시크릿 | 값 |
|---|---|
| `TAP_GITHUB_TOKEN` | `homebrew-tap` 저장소에 `contents: write` 권한이 있는 PAT |

기본 `GITHUB_TOKEN` 은 다른 저장소에 쓸 수 없으므로 별도 토큰이 반드시 필요하다.
Fine-grained personal access token 으로 `homebrew-tap` 저장소만 대상으로 발급하는 것을 권장한다.

```bash
gh secret set TAP_GITHUB_TOKEN --repo yuangunn/image-trigger-clicker
```

## 서명·공증

하지 않는다. `itc` 는 `.app` 번들이 아니라 Homebrew 로 설치되는 CLI 실행 파일이라
Gatekeeper 격리 검사 대상이 아니다. 자세한 내용은 메인 README 의
"코드 서명·공증에 대하여" 절을 보라.
