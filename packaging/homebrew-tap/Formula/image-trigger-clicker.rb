# image-trigger-clicker Homebrew formula
#
# 이 파일은 <계정>/homebrew-tap 저장소의 Formula/ 아래에 놓는다.
# url 과 sha256(최상단 두 줄)은 릴리스마다 update-tap.yml 워크플로가 자동으로 갱신한다.
# resource 스탠자는 `brew update-python-resources image-trigger-clicker` 로 재생성한다.
class ImageTriggerClicker < Formula
  include Language::Python::Virtualenv

  desc "Clicks preset coordinates when a given image appears on screen"
  homepage "https://github.com/yuangunn/image-trigger-clicker"
  url "https://github.com/yuangunn/image-trigger-clicker/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"
  head "https://github.com/yuangunn/image-trigger-clicker.git", branch: "main"

  depends_on "python@3.12"
  depends_on :macos

  # ──────────────────────────────────────────────────────────────────────────
  # opencv-python 대안 (설치가 실패하거나 너무 오래 걸릴 때)
  #
  # 아래 opencv-python resource 는 sdist 를 소스에서 빌드한다. CMake 로 OpenCV
  # 전체를 컴파일하므로 30분 이상 걸리고, 툴체인 문제로 실패하는 일도 잦다.
  # `brew update-python-resources` 가 이 패키지에서 멈추는 경우도 있다.
  #
  # 그럴 때는 Homebrew 가 이미 빌드해 둔 opencv 를 쓴다.
  #   1) 아래 resource "opencv-python" 과 resource "numpy" 블록을 지운다.
  #   2) depends_on 을 추가한다:
  #        depends_on "numpy"
  #        depends_on "opencv"
  #   3) install 을 아래처럼 바꿔서 brew 의 cv2/numpy 를 venv 에서 보이게 한다:
  #
  #        def install
  #          virtualenv_install_with_resources
  #          site = Language::Python.site_packages("python3.12")
  #          (libexec/site/"homebrew-deps.pth").write <<~PTH
  #            #{Formula["opencv"].opt_lib}/#{site}
  #            #{Formula["numpy"].opt_lib}/#{site}
  #          PTH
  #        end
  #
  # 트레이드오프: 설치는 훨씬 빠르고 안정적이지만, brew 의 opencv 가 업그레이드되면
  # 이 도구도 함께 영향을 받는다. 자세한 내용은 tap 저장소의 README 를 보라.
  # ──────────────────────────────────────────────────────────────────────────

  # 아래 resource 목록은 2026-08-14 기준 최신 버전이다.
  # 갱신: brew update-python-resources image-trigger-clicker
  resource "mouseinfo" do
    url "https://files.pythonhosted.org/packages/28/fa/b2ba8229b9381e8f6381c1dcae6f4159a7f72349e414ed19cfbbd1817173/MouseInfo-0.1.3.tar.gz"
    sha256 "2c62fb8885062b8e520a3cce0a297c657adcc08c60952eb05bc8256ef6f7f6e7"
  end

  resource "numpy" do
    url "https://files.pythonhosted.org/packages/9a/80/db0b4559e57ec36362bedbb05530a87fafbcb6067708c946967a41d449e7/numpy-2.5.2.tar.gz"
    sha256 "d482d171c406ae88c5b19cad3b6a1c4c5209f886ab74bc44c2c865c23f52d860"
  end

  # 주의: 소스 빌드에 아주 오래 걸린다. 위 "opencv-python 대안" 주석 참고.
  resource "opencv-python" do
    url "https://files.pythonhosted.org/packages/79/4c/a438d23e09ce2033c09f7b784ad2fbdb0adf529e434101ed28f142226f98/opencv_python-5.0.0.93.tar.gz"
    sha256 "66aac3e5b5faa48d4025816592f3af19e4bfc2c68dec067bae2dbb4ca10aa9e2"
  end

  resource "pillow" do
    url "https://files.pythonhosted.org/packages/1c/3d/bb7fca845737cf9d7dbde16ed1843984665ff2e0a518f5db43e77ec540b9/pillow-12.3.0.tar.gz"
    sha256 "3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce"
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

  def install
    virtualenv_install_with_resources
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
