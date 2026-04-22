# hermes-gpt-image-gen

[English](README.md)

[![Release](https://img.shields.io/github/v/release/Jinbro98/hermes-gpt-image-gen?display_name=tag)](https://github.com/Jinbro98/hermes-gpt-image-gen/releases)
[![License](https://img.shields.io/github/license/Jinbro98/hermes-gpt-image-gen)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-7C3AED)](https://github.com/Jinbro98/hermes-gpt-image-gen)
[![Codex CLI](https://img.shields.io/badge/Codex%20CLI-imagegen-10A37F)](https://developers.openai.com/codex/cli/features/)

**Hermes Agent**용 Codex CLI 기반 이미지 생성 플러그인입니다.

이 플러그인은 Hermes에 `codex_image_generate` 도구를 추가합니다. 내부적으로 Codex CLI의 `$imagegen`을 실행하고, 결과 이미지를 **로컬 파일**로 저장한 뒤 절대 경로를 반환하므로 CLI/로컬 워크플로우에서 재사용하거나 Telegram에서 `MEDIA:/absolute/path` 형식으로 바로 전송할 수 있습니다.

또한 아래와 같은 명시적 요청이 들어오면 Codex 기반 이미지 생성 흐름을 우선 사용하도록 라우팅 힌트를 추가합니다.

- `덕테이프로 ... 이미지 생성해줘`
- `코덱스로 ... 이미지 생성해줘`
- `gpt로 ... 이미지 생성해줘`

---

## 미리보기

### 설치 데모 GIF

![Install demo](assets/install-demo.gif)

### 설치 스크린샷

![Install screenshot](assets/install-screenshot.png)

---

## 주요 기능

- Hermes에 `codex_image_generate` 도구 추가
- 호스팅 이미지 URL 백엔드 대신 **Codex CLI**로 이미지 생성
- Telegram, CLI, 기타 Hermes 워크플로우에 활용 가능한 로컬 파일 경로 반환
- `landscape`, `square`, `portrait` 비율 지원
- `auto`, `transparent`, `opaque` 배경 옵션 지원
- 선택 사항: Hermes 기본 `image_generate`를 Codex 기반 구현으로 교체 가능
- Codex/GPT 계열 이미지 생성 요청에 대한 트리거 기반 라우팅 지원

---

## 요구 사항

설치 전에 아래 항목을 확인하세요.

1. **Hermes Agent**가 이미 설치되어 있어야 합니다.
2. **Codex CLI**가 설치되어 있고 `PATH`에서 실행 가능해야 합니다.
3. Codex 이미지 생성 기능이 활성화되어 있어야 합니다.
4. Codex 인증이 정상 상태여야 합니다.

권장 확인 명령:

```bash
codex --version
codex features list | grep '^image_generation'
```

정상이라면 아래와 비슷한 출력이 보여야 합니다.

```bash
image_generation stable true
```

인증이 꼬였으면 먼저 다시 로그인하세요.

```bash
codex logout
codex login
```

---

## 원라인 설치

```bash
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/install.sh | bash
```

설치 후에는 Hermes를 재시작하거나 새 세션을 시작해야 플러그인이 로드됩니다.

---

## 수동 설치

```bash
mkdir -p ~/.hermes/plugins/codex_image_gen
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/plugin.yaml -o ~/.hermes/plugins/codex_image_gen/plugin.yaml
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/__init__.py -o ~/.hermes/plugins/codex_image_gen/__init__.py
```

그 다음 Hermes를 재시작하거나 세션을 리셋하세요.

---

## 사용 방법

플러그인이 로드되면 Hermes는 아래 도구를 사용할 수 있습니다.

- `codex_image_generate`

예시 payload:

```json
{
  "prompt": "투명 배경의 플랫컬러 귤 아이콘을 만들어줘.",
  "aspect_ratio": "square",
  "background": "transparent",
  "file_name": "tangerine.png"
}
```

성공 시 반환되는 주요 값:

- `image_path`
- `file_name`
- `output_dir`

Telegram 전송 예시:

```text
MEDIA:/absolute/path/to/tangerine.png
```

---

## 트리거 문구

이 플러그인은 명시적인 Codex/GPT 스타일 이미지 생성 요청이 들어오면 라우팅 컨텍스트를 주입합니다.

예시:

- `코덱스로 칠판 이미지 생성해줘`
- `gpt로 귤 아이콘 만들어줘`
- `덕테이프로 강아지 일러스트 제작해줘`

라우팅 힌트는 아래 조건일 때만 활성화됩니다.

- 메시지에 `덕테이프로`, `코덱스로`, `gpt로` 같은 엔진 표현이 포함됨
- 동시에 실제 이미지 생성 요청처럼 보이는 문장이어야 함

---

## 선택 사항: 기본 `image_generate` 교체

Codex CLI가 Hermes 기본 `image_generate`를 대체하게 하려면 **Hermes 시작 전에** 아래 환경 변수를 설정하세요.

```bash
export HERMES_CODEX_IMAGEGEN_OVERRIDE=1
```

이 변수가 켜져 있으면 플러그인이 기존 `image_generate`를 deregister한 뒤, 같은 이름으로 Codex 기반 구현을 다시 등록합니다.

---

## 저장소 구성

이 저장소는 배포에 필요한 최소 파일만 포함합니다.

```text
assets/
  install-demo.gif
  install-screenshot.png
plugin.yaml
__init__.py
README.md
README.ko.md
install.sh
LICENSE
```

---

## 문제 해결

### 플러그인을 설치했는데 Hermes가 사용하지 않음

Hermes/gateway를 재시작하거나 새 세션을 시작하세요.

### `Codex CLI not found in PATH`

Hermes가 실행되는 동일한 환경에서 `codex` 명령이 실행 가능한지 확인하세요.

### `image_generation`을 사용할 수 없음

Codex CLI를 업그레이드하고 인증 상태를 다시 확인하세요.

### Codex 인증 오류가 발생함

아래 명령으로 재로그인해 보세요.

```bash
codex logout
codex login
```

---

## 라이선스

MIT
