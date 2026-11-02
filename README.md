# Reez Rust Output

EEZ Studio의 **실제 C 빌드 결과를 Rust 소스로 변환**하여 함께 출력하는 설치형 확장입니다. 0.3부터는 이전의 제한된 프로젝트 JSON 생성기를 사용하지 않습니다. 테스트 프로젝트에 맞춘 위젯·액션·변수 허용 목록도 없습니다.

평소 Build를 누르면 기존 C 출력은 그대로 생성되고, 같은 C 파일을 C2Rust 0.22.1로 변환한 Cargo 프로젝트가 `rust-src`에 생성됩니다. 변환된 UI 구현은 `.rs`이며 기존 C LVGL·드라이버와 연결합니다. 변환 결과에는 C ABI를 유지하기 위한 `unsafe`, `extern "C"`, `repr(C)` 코드가 포함됩니다.

## 설치

배포 파일은 `artifacts/releases/reez-rust-output-0.3.3.zip`입니다.

**Windows x64에는 WSL과 그 안의 Python 3.11 이상이 필요합니다. 기본 Rust 컴파일 검사에는 WSL의 Rust/Cargo도 필요합니다.** ZIP에는 C2Rust·Clang 실행 라이브러리, LVGL 9.5 헤더와 잠긴 Rust 지원 의존성을 포함합니다. 별도의 Node.js나 MCP 토큰은 필요하지 않습니다. 이전 0.2의 “WSL 없이 실행” 조건은 이 버전에 해당하지 않습니다.

1. **이전 버전이 설치된 PC**는 EEZ Studio를 완전히 종료하고 ZIP을 압축 해제한 뒤 `install.ps1`을 실행합니다. 이 스크립트는 같은 ID의 중복 설치 폴더와 이전 Yarn 등록을 정리합니다.
2. 처음 설치하는 PC는 Extensions Manager의 **Project Editor Extensions**에서 ZIP을 가져올 수 있습니다. 설치 후 Studio를 다시 시작합니다.
3. 위쪽 회색 도구 모음의 **Rust output**을 누르고 프로젝트별 사용을 켭니다.
4. 출력 폴더와 필요하면 실제 C 앱의 `compile_commands.json` 경로를 지정하고 Save를 누릅니다.
5. **Check installation**으로 백엔드를 확인한 뒤 평소 Build를 누릅니다.

검증한 Studio 버전은 Windows EEZ Studio 0.29.0입니다. 기본 설정:

```json
{"enabled": true, "output": "rust-src", "verifyRust": true}
```

설정은 프로젝트 옆 `reez.json`에 저장됩니다. C가 `src/ui`에 출력되면 Rust는 별도의 `rust-src`에 `Cargo.toml`, `Cargo.lock`, `lib.rs`, `src/*.rs`로 나옵니다. `.reez-c-output.json`에는 원본 C 해시와 컴파일 검사 여부가 기록됩니다. 이전 0.2가 관리하던 파일은 새 출력으로 교체하고 사용자 파일은 보존합니다. 충돌하거나 변환에 실패하면 이전 Rust 출력을 유지하고 전체 빌드 성공 메시지를 표시하지 않습니다.

## 헤더·펌웨어 연결

`compile_commands.json`은 C 빌드 시스템이 각 `.c` 파일에 사용한 컴파일러 옵션, 헤더 경로, 매크로를 기록한 JSON 파일입니다. **PC GUI 테스트에서는 입력란을 비워 두면 됩니다.** ESP32/STM32 펌웨어에 연결할 때는 해당 보드 프로젝트가 생성한 파일을 지정하세요.

실제 앱 빌드의 **LVGL 버전, `lv_conf.h`, include 경로, 매크로와 타깃**이 일치해야 합니다. CMake 앱에서는 `CMAKE_EXPORT_COMPILE_COMMANDS=ON`으로 생성한 compilation database를 지정하는 것이 좋습니다. 해당 파일은 EEZ C 출력 디렉터리의 모든 `.c`를 포함해야 합니다.

경로를 비우면 번들 LVGL 9.5 데스크톱 헤더 설정을 사용합니다. 이 설정의 Rust 컴파일 성공은 보드별 ABI나 펌웨어 링크 성공을 보장하지 않습니다. 다른 LVGL 버전/설정과 임베디드 타깃은 실제 compilation database를 사용하세요. `rustTarget`, `rustToolchain`도 JSON에서 지정할 수 있습니다.

생성 crate를 Rust 앱의 의존성으로 연결하거나 정적 라이브러리로 빌드하여 기존 C LVGL에 링크합니다. 원본 C UI 정의는 중복 링크하지 않습니다. C 헤더에 선언만 있는 네이티브 액션·외부 폰트는 앱이 실제 구현을 제공해야 하며, 변환기는 빈 구현을 만들지 않습니다. `std` 기능을 끄는 인터페이스를 제공하지만, 모든 C 입력의 `no_std` 변환이나 ESP32/STM32 실기기 실행을 검증한 것은 아닙니다.

**C++ 변환은 지원하지 않습니다.** C++ 파일이나 EEZ Flow C++ 런타임이 있으면 생략하지 않고 오류를 표시합니다. C2Rust가 지원하지 않는 C 문법도 오류로 처리합니다. 모든 EEZ C/C++ 프로젝트의 무조건적인 변환을 보장하는 도구는 아닙니다. 상세 조건은 [SUPPORT.md](integration/SUPPORT.md), 구조는 [백엔드 문서](docs/c-output-backend.md)에 있습니다.

## 개발·패키징

프로젝트는 `.python-version`, `pyproject.toml`, `uv.lock`과 Cargo/npm 잠금 파일을 유지합니다.

```sh
uv sync --locked
uv run --locked rustup component add rust-docs
# LLVM/Clang 개발 패키지 설치 후 예시:
LLVM_CONFIG_PATH=/usr/bin/llvm-config-18 uv run --locked python tools/setup_c2rust.py
LLVM_CONFIG_PATH=/usr/bin/llvm-config-18 uv run --locked python tools/build_release.py
uv run --locked python tools/package.py
uv run --locked node --test tests/studio.test.cjs
uv run --locked pytest -q tests/test_packaged_c_backend.py tests/test_package.py
```

개발용 C2Rust는 `.tools/c2rust`에 버전 0.22.1과 upstream Cargo.lock을 사용해 설치합니다. LVGL 9.5 헤더는 고정 커밋을 사용하며 `REEZ_LVGL`로 기존 체크아웃을 지정할 수 있습니다. 완성 ZIP은 동일 이름으로 덮어쓰지 않습니다. `tools/install_studio.py`로 현재 사용자에게 설치하거나 `--extensions`로 시험 경로에 설치할 수 있습니다.

C/Rust LVGL 화면 비교는 `tools/validate_c_output.py`를 사용합니다. 이 로컬 검증에는 `../wokwipj`의 LVGL/생성 C와 SDL2 개발 환경이 필요합니다. 해당 프로젝트는 시험 입력일 뿐 변환기의 지원 대상을 제한하지 않습니다.

이전 JSON 생성기와 그 API에 연결된 모니터 데모는 참고용 소스로 남아 있습니다. `tools/validate_firmware.py`는 이전 출력 형식용이므로 새 C 변환 결과 검증에는 사용하지 않습니다. Rust 통신·제어 코어는 `crates/controller`, PC HTTP 시험 서버는 `crates/firmware-host`에 있습니다.

## 빌드 용량

개발 프로필은 `debug=0`, `incremental=true`, `lto=false`를 사용합니다. 상세 디버깅은 `--profile dev-debug`를 선택합니다. Windows/WSL의 target을 공유하거나 매번 clean하지 않습니다. 변환 결과의 Cargo 검사 캐시는 WSL의 `~/.cache/reez/c-output/target`에서 재사용합니다. C2Rust 설치 중간 산출물은 배포 ZIP에 포함하지 않습니다.

Reez 도구는 MIT, EEZ Studio 어댑터는 GPL-3.0-only입니다. 배포 ZIP은 소스·제3자 고지와 필요한 대응 소스를 포함합니다.
