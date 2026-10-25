# Reez Rust Output

EEZ Studio의 기존 Build에 Rust UI 생성을 추가하는 설치형 확장입니다. **배포 ZIP 하나에 Rust WebAssembly 생성기와 폰트 변환기를 포함**하며, 사용자는 Rust·Node.js·Python·WSL을 설치할 필요가 없습니다. EEZ Studio의 내장 런타임에서 실행합니다.

## 사용자 설치

배포 파일: `artifacts/releases/reez-rust-output-0.2.0.zip`과 같은 이름의 `.zip.sha256` 체크섬 파일입니다. 이 ZIP을 다른 사용자에게 전달하면 됩니다.

1. EEZ Studio의 Extensions Manager에서 로컬 ZIP 설치 기능을 선택합니다.
2. `reez-rust-output-0.2.0.zip`을 가져옵니다.
3. 작업을 저장하고 EEZ Studio를 재시작합니다.
4. 저장된 프로젝트를 열고 오른쪽 위 **Rust output** 버튼을 누릅니다.
5. **Enable Rust output for this project**를 켜고 출력 폴더를 정한 뒤 Save를 누릅니다. 기본값은 `rust-src`입니다.
6. 평소 **Build** 버튼을 누릅니다. 기존 C/C++ 출력과 Rust 출력이 함께 생성됩니다.

**Check installation**은 생성기 버전을 확인합니다. 빌드 로그에 `Rust output:`이 표시되면 정상입니다. 새 프로젝트는 사용자가 활성화할 때까지 기존 빌드만 수행합니다.

Windows에서는 ZIP을 풀고 포함된 `install.ps1`을 PowerShell에서 실행해 현재 사용자에게 설치할 수도 있습니다. 관리자 권한은 필요하지 않습니다. 스크립트 실행이 제한된 환경에서는 Extensions Manager를 사용합니다. 설치 위치는 `%APPDATA%\eezstudio\extensions\reez-rust-output`입니다. 프로그램 본체와 `app.asar`는 수정하지 않습니다.

업데이트는 새 ZIP을 설치하고 Studio를 재시작하면 됩니다. 제거는 Studio를 닫은 뒤 `install.ps1 -Uninstall` 또는 해당 확장 폴더만 삭제합니다. 프로젝트 설정과 생성 파일은 유지됩니다.

## 프로젝트 설정과 출력

프로젝트 폴더의 `reez.json`은 설정 화면에서 생성하며 다른 PC에서도 그대로 쓸 수 있습니다.

```json
{"enabled": true, "output": "rust-src"}
```

개인 계정명, 생성기 절대 경로, MCP 토큰, WSL 배포판 이름이 필요하지 않습니다. 기존 `executable`, `args`, `environment`, `wslDistro` 고급 설정은 명시적으로 사용한 경우 계속 지원합니다.

예를 들어 C/C++는 기존 `src/ui`, Rust는 `rust-src`에 출력됩니다. Rust 출력은 `mod.rs`, `screens.rs`, `styles.rs`, `resources.rs`이며 폰트도 Rust 바이트 배열로 포함됩니다. C 생성 코드를 변환하는 방식이 아니라 EEZ 프로젝트 JSON을 직접 읽습니다.

확장은 현재 편집 상태를 직렬화합니다. C 빌드 도중 프로젝트가 바뀌면 재빌드를 요구합니다. Rust 실패 시 이전 Rust 출력은 유지하며 전체 성공 메시지를 표시하지 않습니다. C 출력은 이미 갱신되었을 수 있습니다.

## 지원 범위

검증 환경은 **Windows x64, EEZ Studio 0.29.0, LVGL 9.5.0, Flow 비활성화**입니다. 확장 ZIP의 생성기 자체는 OS에 독립적인 WebAssembly입니다. Windows에서 EEZ 내장 런타임을 이용한 실제 실행을 검증했습니다.

첫 버전은 화면·컨테이너·버튼·라벨, 좌표·크기, 리터럴 텍스트·플래그·상태, 테스트 화면의 로컬 스타일, 단일 소스 폰트를 지원합니다. EEZ Flow, 선언 액션·전역 변수·표현식, 이미지 위젯, 사용자 위젯, 공유/조건부 스타일, 입력 그룹, 프로젝트 import는 오류로 보고합니다. 현재 액션과 상태 연결은 앱의 Rust 콜백·상태로 작성합니다.

생성된 Rust UI는 **기존 C LVGL에 연결**합니다. 별도의 순수 Rust LVGL 엔진이나 보드 HAL을 제공하지 않습니다. 확장 설치만으로 펌웨어를 컴파일하는 것은 아니며, ESP32·STM32에서는 플랫폼별 툴체인·디스플레이·입력·시간 공급·링크 설정이 필요합니다.

출력 파일은 `.reez-manifest.json`으로 관리합니다. 사용자 파일은 보존하며 충돌하면 덮어쓰지 않습니다. 내용이 같으면 파일을 다시 쓰지 않습니다. 중단 후 `.rust-src.reez-lock`이 남으면 실행 중인 생성기가 없는지 확인한 뒤 그 잠금 파일만 제거합니다.

## 개발과 배포 파일 만들기

개발자는 uv, Rust 1.99.1, Node/npm을 준비합니다. 사용자의 설치 환경에는 이 도구들이 필요하지 않습니다.

```bash
uv sync --locked
uv run --locked npm ci
uv run --locked rustup target add wasm32-wasip1 --toolchain 1.99.1
uv run --locked python tools/build_release.py
uv run --locked python tools/package.py
```

배포 도구는 Rust 표준 라이브러리의 저작권 고지를 포함하므로 빌드 툴체인의 `rust-docs` 구성 요소가 필요합니다. 없으면 `uv run --locked rustup component add rust-docs`로 추가합니다. Rust와 Node 의존성은 각각 `Cargo.lock`, `package-lock.json`으로 고정합니다.

`tools/package.py`는 완성된 ZIP과 SHA-256 체크섬, 생성기 소스, 확장 소스, 의존성 라이선스를 묶습니다. 같은 이름의 기존 배포 파일은 덮어쓰지 않으므로 재검토 중에는 `--out <새 폴더>`를 사용합니다. `.github/workflows/package.yml`은 수동 실행 또는 버전 태그에서 빌드·검증 후 다운로드 가능한 artifact를 만듭니다. 공개 릴리스 업로드는 자동으로 하지 않습니다.

개발 환경에서 설치하려면:

```bash
uv run --locked python tools/install_studio.py
# 사용자 경로는 자동 감지합니다. 별도 테스트 설치 경로도 지정할 수 있습니다.
uv run --locked python tools/install_studio.py --extensions /path/to/eezstudio/extensions
```

기존 프로젝트의 WSL 실행 설정을 배포형 런타임으로 바꾸려면 `--project /path/project.eez-project --use-bundled`를 지정합니다. 기존 실행 설정은 `.json.before-portable` 파일로 보관합니다.

## 개발 검증

```bash
uv run --locked cargo build --locked -p reez
uv run --locked cargo test --locked -p reez
uv run --locked node --test tests/studio.test.cjs
uv run --locked pytest -q tests/test_generator.py -k 'not without_std'
uv run --locked pytest -q tests/test_package.py
```

배포 시험은 ZIP을 새 경로에 풀어 외부 도구가 없는 PATH에서 실행하고, 설치·업데이트·실패 시 복구·사용자 파일 보존을 검사합니다. `tools/check_package.py`는 WSL 개발 환경에서 실제 Windows EEZ 런타임으로 배포본의 버전·한글 폰트·114개 객체 생성 및 네이티브/WASM 출력 일치를 검증합니다. `tools/check_studio.py`는 실제 Studio의 동시 출력과 오류 처리를 검증합니다. 이 두 로컬 통합 도구의 기본값은 개발자의 설치 경로이며 필요하면 인자를 지정하거나 해당 스크립트를 조정합니다.

## PC 모니터 앱과 LVGL 연결

전체 모니터 통합 시험에는 기존 `../wokwipj`, LVGL 소스, 테스트 EEZ 프로젝트, C 컴파일러, libclang, SDL2 개발 라이브러리가 필요합니다.

```bash
uv run --locked python tools/project.py setup
uv run --locked python tools/project.py build
uv run --locked python tools/project.py test
uv run --locked python tools/project.py lint
```

LVGL 소스는 `REEZ_LVGL`, EEZ 입력은 `EEZ_PROJECT`, 모니터 레지스터 정의는 `WOKWI_PROJECT`로 지정합니다. 고정 LVGL 커밋은 `tools/dependencies.json`에 있습니다. 기존 시험 폴더에서 두 터미널을 사용합니다.

```bash
# ../wokwipj, 터미널 1
uv run --locked python tools/project.py demo
# ../wokwipj, 터미널 2
uv run --locked python tools/reez.py run
```

Rust 앱 재빌드는 `tools/reez.py build`, 기존 28개 시험을 Rust 대상으로 실행하려면 `tools/reez.py test -q`입니다. 기본 C 시험 명령도 유지합니다. UI·설정·차트·경보·HTTP 앱 로직은 Rust이며 LVGL·SDL과 기존 모의 서버를 재사용합니다. 검증 범위는 PC GUI이며 MCU 실행이나 실기기 검증을 의미하지 않습니다.

생성기를 네이티브 개발 도구로 직접 사용할 수도 있습니다.

```bash
uv run --locked cargo run --locked -p reez -- --project /path/project.eez-project --out /path/rust-src
uv run --locked cargo run --locked -p reez -- --project /path/project.eez-project --check
```

`--check`는 지원 기능 검사이며 폰트 변환은 실제 생성을 실행해야 검사합니다. 오류는 stderr의 JSON `path`, `message`와 종료 코드로 반환합니다. `--prepared-fonts`는 확장 런타임이 변환한 폰트를 전달하는 내부 연동 옵션입니다.

앱에서 `reez-lvgl`과 생성 모듈을 연결합니다.

```rust
#[path = "../rust-src/mod.rs"]
mod generated;
// 플랫폼의 LVGL·디스플레이·입력 초기화 후, 같은 UI 스레드에서:
let ui = unsafe { generated::Ui::create() };
unsafe { ui.load_screen(1) };
let label = ui.object("current_temp").unwrap();
unsafe { reez_lvgl::text(label, "23.5") };
```

연결 crate와 생성 코드는 `no_std + alloc`에 호환됩니다. raw LVGL 포인터를 노출하므로 접근은 unsafe 계약을 따릅니다. 객체를 외부에서 삭제하지 않고, UI를 소유한 스레드에서만 사용하며, `Ui`보다 디스플레이가 오래 살아 있어야 합니다. 임베디드에서는 `reez-lvgl`의 `default-features = false`, `REEZ_LV_CONF`, `REEZ_LVGL_LIB`와 타깃별 libclang 설정을 제공해야 합니다. 헤더·설정·라이브러리·타깃은 일치해야 합니다.

## 빌드 용량과 라이선스

dev/test는 `debug=0`, `incremental=true`, `lto=false`입니다. 상세 디버깅은 `--profile dev-debug`를 사용하며 자동 clean은 하지 않습니다. WSL 캐시는 Linux 파일시스템에 두고 Windows와 공유하지 않습니다. LVGL 예제·데모·ThorVG는 빌드하지 않습니다.

2026-10-25 Rust 1.99.1의 독립 캐시 비교에서 target은 491.0 MiB에서 275.4 MiB로 약 44% 감소했고, 초기 빌드 21.573→21.305초, 수정 후 빌드 중앙값 0.479→0.444초였습니다. `tools/benchmark.py`로 재측정할 수 있습니다. Clippy·테스트·WebAssembly 빌드를 함께 수행한 실제 개발 캐시는 이 측정보다 커질 수 있습니다.

Rust 생성기와 개발 도구는 MIT, Studio 확장은 GPL-3.0-only입니다. 배포본은 원본 소스와 제3자 라이선스를 포함합니다. LVGL·SDL·사용자 폰트는 각각의 라이선스를 따릅니다.
