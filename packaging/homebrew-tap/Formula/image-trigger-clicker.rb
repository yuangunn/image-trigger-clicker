# image-trigger-clicker Homebrew formula
#
# 이 파일은 <계정>/homebrew-tap 저장소의 Formula/ 아래에 놓는다.
# url 과 sha256(최상단 두 줄)은 태그를 밀 때 update-tap.yml 워크플로가 자동으로 갱신한다.
class ImageTriggerClicker < Formula
  include Language::Python::Virtualenv

  desc "Clicks preset coordinates when a given image appears on screen"
  homepage "https://github.com/yuangunn/image-trigger-clicker"
  url "https://github.com/yuangunn/image-trigger-clicker/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "7b4590cfe5688371e23715970b25867e825e890b2fb5092836cb8e6b9cfc253b"
  license "MIT"
  head "https://github.com/yuangunn/image-trigger-clicker.git", branch: "main"

  depends_on "python@3.12"
  depends_on :macos

  # ──────────────────────────────────────────────────────────────────────────
  # 휠(wheel)로 받는 의존성: numpy / opencv-python / pillow
  #
  # 이 셋은 sdist 소스 빌드가 현실적이지 않다.
  #   - opencv-python : CMake 로 OpenCV 전체를 빌드한다(30~60분, 자주 실패).
  #   - numpy         : Apple clang 으로 컴파일이 깨진다. Homebrew 의 numpy formula
  #                     자체가 `depends_on "gcc" => :build` 로 gcc 를 쓴다.
  #   - pillow        : jpeg/tiff/webp 등 이미지 라이브러리 헤더를 요구한다.
  #
  # 실제로 v0.1.0 을 resource(sdist) 방식으로 설치해 봤다가 11분 만에
  # numpy 2.5.2 컴파일 오류(string_fastsearch.h 템플릿 치환 실패)로 깨졌다.
  # 그래서 이 셋만 공식 배포 휠을 그대로 설치한다.
  #
  # 검토했지만 채택하지 않은 대안: depends_on "opencv" (+ "numpy", "pillow")
  #   Homebrew 가 미리 빌드해 둔 bottle 을 쓰므로 빠르고 안정적이다. 다만 brew 의
  #   opencv 5.0 은 Qt / VTK / OpenVINO / ffmpeg / tesseract / gcc 까지 의존
  #   formula 106개를 끌고 온다(수 GB). cv2.matchTemplate 하나 때문에 치르기엔
  #   과한 비용이라 쓰지 않았다. 순정 Homebrew 구성을 원하면 이 방식으로 바꾸고
  #   venv 에 brew 의 site-packages 를 .pth 로 노출하면 된다.
  #   이때 brew 의 opencv 는 python@3.14 용으로 빌드되므로 위 depends_on 도
  #   python@3.14 로 맞춰야 한다.
  # ──────────────────────────────────────────────────────────────────────────
  on_arm do
    resource "numpy" do
      url "https://files.pythonhosted.org/packages/60/2e/b5aee50a1f74ac815cf8331812cb8251e29024025de462e0c047641c614c/numpy-2.5.2-cp312-cp312-macosx_11_0_arm64.whl"
      sha256 "4bbd96c833ecc8cc069ce518078fc8c60cb9cbfb0fea5b7a803ad65035596d03"
    end

    resource "opencv-python" do
      url "https://files.pythonhosted.org/packages/9c/75/76f6ade78f6102c61034f828e2a22616708df2c9504bc8d6af9dd8f73dc5/opencv_python-5.0.0.93-cp37-abi3-macosx_13_0_arm64.whl"
      sha256 "198a75138241810206a17c829dbcc40a7cb1841cda538ca86cbbfc6c7d95f898"
    end

    resource "pillow" do
      url "https://files.pythonhosted.org/packages/d8/66/9a386a92561f402389a4fc70c18838bf6d35eb5eb5c6850b4b2dc64f5048/pillow-12.3.0-cp312-cp312-macosx_11_0_arm64.whl"
      sha256 "ffd0c5368496f41b0944be820fcb7a838aa6e623d250b01acf2643939c3f99d7"
    end
  end

  on_intel do
    resource "numpy" do
      url "https://files.pythonhosted.org/packages/69/72/dccb0aaf40972777283303919f613964227266d0c13adebb79ac124f1c3e/numpy-2.5.2-cp312-cp312-macosx_10_13_x86_64.whl"
      sha256 "14e373cfc6387177e8409dac3c7159be8eb05cd77096cd7c950268b86f62831c"
    end

    resource "opencv-python" do
      url "https://files.pythonhosted.org/packages/15/8c/bc1bda6aae69a32e9d84fc34153ba104cd25226861eb4aea33b2cea4860d/opencv_python-5.0.0.93-cp37-abi3-macosx_14_0_x86_64.whl"
      sha256 "6bbc32f59e1b1a7db7b39c81f63d00625f041d333037fd8702f6da52cc39108b"
    end

    resource "pillow" do
      url "https://files.pythonhosted.org/packages/37/bf/fb3ebff8ddcb76aac5a01389251bbbb9519922a9b520d8247c1ca864a25d/pillow-12.3.0-cp312-cp312-macosx_10_13_x86_64.whl"
      sha256 "ba09209fbe443b4acccebe845d8a138b89a8f4fbaeedd44953490b5315d5e965"
    end
  end

  # ── 소스(sdist)에서 빌드하는 의존성 ──
  # 갱신: brew update-python-resources image-trigger-clicker
  #       실행 후 numpy / opencv-python / pillow 블록은 위 휠 형태로 되돌릴 것.
  #       (2026-08-14 기준 버전)
  resource "mouseinfo" do
    url "https://files.pythonhosted.org/packages/28/fa/b2ba8229b9381e8f6381c1dcae6f4159a7f72349e414ed19cfbbd1817173/MouseInfo-0.1.3.tar.gz"
    sha256 "2c62fb8885062b8e520a3cce0a297c657adcc08c60952eb05bc8256ef6f7f6e7"
  end

  resource "pyautogui" do
    url "https://files.pythonhosted.org/packages/65/ff/cdae0a8c2118a0de74b6cf4cbcdcaf8fd25857e6c3f205ce4b1794b27814/PyAutoGUI-0.9.54.tar.gz"
    sha256 "dd1d29e8fd118941cb193f74df57e5c6ff8e9253b99c7b04f39cfc69f3ae04b2"
  end

  resource "pygetwindow" do
    url "https://files.pythonhosted.org/packages/e1/70/c7a4f46dbf06048c6d57d9489b8e0f9c4c3d36b7479f03c5ca97eaa2541d/PyGetWindow-0.0.9.tar.gz"
    sha256 "17894355e7d2b305cd832d717708384017c1698a90ce24f6f7fbf0242dd0a688"
  end

  resource "pymsgbox" do
    url "https://files.pythonhosted.org/packages/ae/6a/e80da7594ee598a776972d09e2813df2b06b3bc29218f440631dfa7c78a8/pymsgbox-2.0.1.tar.gz"
    sha256 "98d055c49a511dcc10fa08c3043e7102d468f5e4b3a83c6d3c61df722c7d798d"
  end

  resource "pyobjc-core" do
    url "https://files.pythonhosted.org/packages/a5/78/abc4ce5920305780aeb36b4067a86253378b36e29ba96673a3deb02eb03a/pyobjc_core-12.2.2.tar.gz"
    sha256 "3906452339cd06a3bb07df103c2511d4cb0f7a22d8771c0b802eba15d9a642b6"
  end

  resource "pyobjc-framework-Cocoa" do
    url "https://files.pythonhosted.org/packages/75/76/49c6da2c6a831020b4854ba20079d5a1030474bffc776b7b73c2eeff8c15/pyobjc_framework_cocoa-12.2.2.tar.gz"
    sha256 "c96c0ef69a71afbbb0e6a7d594b455c5fe47d62e0db376ee7a2b4b828c16ace9"
  end

  resource "pyobjc-framework-Quartz" do
    url "https://files.pythonhosted.org/packages/35/b1/426a37c7ae37280b3ffca2571fb48f211946aee2f4ca31a603ed1943c4a7/pyobjc_framework_quartz-12.2.2.tar.gz"
    sha256 "810f97b210cfd93704d240860286dfd6df09f9f1c52525fc5c2166723aea3f9e"
  end

  resource "pyperclip" do
    url "https://files.pythonhosted.org/packages/e8/52/d87eba7cb129b81563019d1679026e7a112ef76855d6159d24754dbd2a51/pyperclip-1.11.0.tar.gz"
    sha256 "244035963e4428530d9e3a6101a1ef97209c6825edab1567beac148ccc1db1b6"
  end

  resource "pyrect" do
    url "https://files.pythonhosted.org/packages/cb/04/2ba023d5f771b645f7be0c281cdacdcd939fe13d1deb331fc5ed1a6b3a98/PyRect-0.2.0.tar.gz"
    sha256 "f65155f6df9b929b67caffbd57c0947c5ae5449d3b580d178074bffb47a09b78"
  end

  resource "pyscreeze" do
    url "https://files.pythonhosted.org/packages/ee/f0/cb456ac4f1a73723d5b866933b7986f02bacea27516629c00f8e7da94c2d/pyscreeze-1.0.1.tar.gz"
    sha256 "cf1662710f1b46aa5ff229ee23f367da9e20af4a78e6e365bee973cad0ead4be"
  end

  resource "pytweening" do
    url "https://files.pythonhosted.org/packages/79/0c/c16bc93ac2755bac0066a8ecbd2a2931a1735a6fffd99a2b9681c7e83e90/pytweening-1.2.0.tar.gz"
    sha256 "243318b7736698066c5f362ec5c2b6434ecf4297c3c8e7caa8abfe6af4cac71b"
  end

  resource "rubicon-objc" do
    url "https://files.pythonhosted.org/packages/0d/26/3e6bb0bfd41ff446d29931205088556055ec18c31bf099d6719c281c448c/rubicon_objc-0.5.6.tar.gz"
    sha256 "0d3b0a9889f72916c095a58e7e1c275c260cb8a86b8ef8b909e60cb002fd54d5"
  end

  # 휠로 설치할 resource 이름. install 에서 sdist 목록과 갈라내는 데 쓴다.
  WHEEL_RESOURCES = %w[numpy opencv-python pillow].freeze

  def install
    venv = virtualenv_create(libexec, "python3.12")

    # Homebrew 는 내려받은 파일을 캐시에 "<sha256>--원래이름" 으로 저장한다.
    # pip 는 그 이름을 잘못된 휠 파일명으로 보고 거부하므로, 원래 이름으로
    # 복사한 뒤 넘긴다. (pip 는 --no-binary=:all: 이어도 명시적으로 준
    # 로컬 .whl 파일은 그대로 설치한다.)
    wheels = WHEEL_RESOURCES.map do |name|
      resource_to_install = resource(name)
      wheel = buildpath/resource_to_install.url.split("/").last
      cp resource_to_install.cached_download, wheel
      wheel
    end
    venv.pip_install wheels

    venv.pip_install resources.reject { |r| WHEEL_RESOURCES.include?(r.name) }
    venv.pip_install_and_link buildpath
  end

  def caveats
    <<~EOS
      실행 전에 macOS 권한을 허용해야 합니다.
        시스템 설정 > 개인정보 보호 및 보안 > 화면 기록
        시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용

      권한은 itc 실행 파일이 아니라 itc 를 실행하는 "터미널 앱"에 부여됩니다.
      터미널 앱을 바꾸면 새 앱에 대해 다시 허용해야 합니다.

      먼저 아래를 실행해 환경을 점검하세요:
        itc init
        itc doctor
    EOS
  end

  test do
    assert_match "image-trigger-clicker #{version}", shell_output("#{bin}/itc --version")

    # 의존성이 실제로 임포트되는지 (opencv 없으면 confidence 매칭이 안 된다)
    system libexec/"bin/python", "-c", "import cv2, numpy, PIL, pyautogui"

    # 화면 접근 없이 확인할 수 있는 경로만 테스트한다.
    # (CI 샌드박스에는 화면 기록 권한이 없어 run/test/pos 는 쓸 수 없다.)
    system bin/"itc", "init", "--config", testpath/"config.toml"
    assert_path_exists testpath/"config.toml"
    assert_path_exists testpath/"images"

    # 잘못된 설정은 종료 코드 2 로 끝나야 한다.
    (testpath/"bad.toml").write <<~TOML
      [profiles.p]
      [[profiles.p.targets]]
      name = "t"
      image = "a.png"
      click = { mode = "nope" }
    TOML
    output = shell_output("#{bin}/itc run --config #{testpath}/bad.toml 2>&1", 2)
    assert_match "click.mode", output
  end
end
