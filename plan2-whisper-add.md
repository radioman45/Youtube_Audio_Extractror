# faster-whisper 로컬 자막 추가 계획

## 목표

- YouTube URL 하나를 입력받아 오디오를 내려받고, 로컬 `faster-whisper`로 SRT 자막을 생성하는 기능을 추가한다.
- 기존 FastAPI 웹앱의 현재 구조를 유지하면서, 같은 기능을 재사용하는 CLI 엔트리포인트도 만든다.
- 기존 "유튜브 제공 자막 다운로드" 기능은 그대로 유지하고, Whisper는 별도 분기만 추가한다.
- 이번 단계에서는 계획만 작성하고 구현은 하지 않는다.

## 현재 구조 요약

- 활성 앱 경로는 Python/FastAPI 기준이다.
  - [`app/main.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\main.py)
  - [`app/models.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\models.py)
  - [`app/services/extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\extractor.py)
  - [`app/services/subtitle_extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\subtitle_extractor.py)
  - [`app/static/index.html`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\index.html)
  - [`app/static/app.js`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\app.js)
- 현재 `subtitle` 모드는 YouTube에 이미 존재하는 자막/자동자막을 받아 `.srt`로 변환하는 구조다.
- 오디오 다운로드, ffmpeg 실행, 임시 디렉터리 정리, 진행률 보고는 이미 [`app/services/extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\extractor.py)에 기반이 있다.
- 저장소에는 예전 Node 경로(`src/`, `public/`)도 있지만, 이번 작업 대상은 FastAPI 앱 기준으로 잡는 것이 맞다.

## 권장 설계

### 1. 새 서비스 추가

- 새 파일: `app/services/whisper_subtitle_extractor.py`
- 역할:
  - 입력 옵션 검증
  - YouTube 오디오 다운로드
  - Whisper 입력용 WAV 정규화
  - 장시간 영상 chunk 분할
  - `faster-whisper` 전사
  - SRT 렌더링
  - 결과 파일 반환

예상 데이터 구조:

- `WhisperSubtitleOptions`
  - `url: str`
  - `model: Literal["tiny", "base", "small", "medium", "large", "large-v3", "large-v3-turbo"]`
  - `language: str = "ko"`
  - `output_format: Literal["srt"] = "srt"`
  - `vad_filter: bool = True`
  - `start_time: str | None = None`
  - `end_time: str | None = None`

### 2. 기존 extractor 유틸 재사용

- [`app/services/extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\extractor.py)에서 이미 있는 아래 로직은 재사용한다.
  - `validate_youtube_url`
  - `parse_time_to_seconds`
  - `probe_media_info`
  - `download_source_audio`
  - `run_ffmpeg`
  - `cleanup_temp_dir`
  - `notify_progress`
- 필요한 경우 아래 helper만 추가한다.
  - Whisper 전용 WAV 변환 helper
  - 긴 WAV 분할 helper

핵심 원칙:

- yt-dlp 다운로드 로직을 새로 중복 구현하지 않는다.
- ffmpeg 실행도 기존 패턴을 유지한다.
- Whisper 쪽만 서비스 모듈로 분리한다.

### 3. CLI는 얇은 엔트리포인트로 구현

- 새 파일: `extractor.py`
- 구현 방식: `argparse`
  - 현재 저장소는 Python 표준 라이브러리 중심이고, 별도 CLI 프레임워크 의존이 없다.
  - 단일 스크립트 요구와 배포 단순성을 고려하면 `Click`보다 `argparse`가 맞다.

필수 CLI 옵션:

- `--url`
- `--model`
  - choices:
    - `tiny`
    - `base`
    - `small`
    - `medium`
    - `large`
    - `large-v3`
    - `large-v3-turbo`
- `--language` 기본값 `ko`
- `--output-format` 기본값 `srt` 고정 검증
- `--vad-filter` / `--no-vad-filter`

CLI 동작:

- 내부적으로 `WhisperSubtitleOptions`를 만들고 서비스 함수를 호출한다.
- 완료 시 생성된 `.srt` 파일 경로를 출력한다.
- 실패 시 명확한 에러 메시지와 종료 코드 비정상 반환을 준다.
- 코드 상단 주석에 사용자 요청대로 설치 예시를 넣는다.
  - `pip install yt-dlp faster-whisper ffmpeg`

주의:

- 위 주석은 사용자 요청 그대로 넣더라도, 실제 ffmpeg 실행은 현재 프로젝트처럼 시스템 ffmpeg 또는 `imageio-ffmpeg` 해석 로직을 유지하는 편이 안전하다.

## 전사 처리 흐름

### 1. 입력 검증

- URL 검증은 기존 YouTube URL 검증 재사용
- 시간 범위 검증 재사용
- 모델명은 고정 choices 검증
- `output_format`은 이번 범위에서 `srt`만 허용

### 2. 오디오 준비

- yt-dlp로 원본 오디오 다운로드
- ffmpeg로 Whisper 입력용 WAV로 정규화
  - 권장 포맷:
    - PCM 16-bit
    - mono
    - 16kHz 또는 16k/일관된 샘플레이트

### 3. 장시간 영상 chunk 처리

- 3~4시간 영상 대응을 위해 전체 WAV를 한 번에 메모리에 올리지 않는다.
- 기본 전략:
  - 일정 길이 단위로 WAV 분할
  - chunk별 순차 전사
  - chunk 시작 오프셋을 전역 타임스탬프에 합산
  - 마지막에 단일 `.srt`로 병합

권장 기준:

- 30분 단위 chunk
- 90분 이상이거나 파일 크기가 큰 경우 chunk 모드 강제

권장 병합 규칙:

- 각 chunk의 segment 시작/종료 시간에 `chunk_offset_seconds`를 더한다.
- segment 번호는 마지막에 전체 기준으로 다시 1부터 매긴다.

선택적 보강:

- chunk 경계 단어 유실 방지를 위해 아주 짧은 overlap을 둘 수 있다.
- 다만 1차 구현은 복잡도를 낮추기 위해 overlap 없이 시작해도 된다.

### 4. faster-whisper 실행

- 모델은 한 번만 로드하고 chunk들을 순차 처리한다.
- 전사 옵션:
  - `language=<cli_or_ui_value>`
  - `vad_filter=<bool>`
- 출력은 segment 리스트를 받아 SRT로 렌더링한다.

### 5. 결과 반환

- 최종 `.srt` 파일 생성
- 웹앱에서는 `ExtractionResult` 반환
- CLI에서는 성공 메시지와 경로 출력

## 오프라인 요구사항 처리

사용자 요구사항에 "Whisper는 인터넷 없이 로컬 실행"이 포함되어 있으므로, 구현 시 아래 정책을 따른다.

- 전사 실행 자체는 OpenAI API 없이 로컬 `faster-whisper`만 사용한다.
- 모델이 로컬에 없을 때 자동 네트워크 다운로드에 기대지 않는다.
- 모델 미존재 시:
  - 명확한 오류 메시지로 종료하거나
  - 문서에 사전 모델 준비 절차를 안내한다.

즉, "처음 실행 시 모델을 인터넷에서 받아오게 두는 방식"은 사용자 요구와 충돌할 수 있으므로 피하는 것이 맞다.

## 웹 UI 반영안

### 권장 방식: 기존 `subtitle` 모드 안에 "자막 방식" 추가

새 탭을 추가하는 것보다, 현재 자막 모드 안에 소스 선택을 넣는 편이 자연스럽다.

추가 UI 필드:

- `자막 방식`
  - `YouTube 자막 다운로드`
  - `Whisper 로컬 생성`
- `Whisper 모델`
  - `tiny`, `base`, `small`, `medium`, `large`, `large-v3`, `large-v3-turbo`
- `언어`
  - 기존 `subtitleLanguage` 재사용 가능
- `VAD 필터`
  - 체크박스
- 안내 문구
  - 저사양: `tiny`, `base`
  - 고사양: `large-v3-turbo`

표시 규칙:

- `subtitle` 모드에서만 `자막 방식` 필드를 노출
- `Whisper 로컬 생성` 선택 시:
  - 모델 선택 필드 표시
  - VAD 필드 표시
  - "결과는 SRT로 생성됩니다" 안내 표시
- `YouTube 자막 다운로드` 선택 시:
  - 현재 UI 동작 유지

### 배치 모드 처리

1차 구현 권장 범위:

- 배치 모드의 `subtitle`은 현재처럼 YouTube 자막 다운로드만 유지
- Whisper 자막은 우선 단일 영상 `subtitle` 모드에서만 지원

이유:

- 긴 영상 chunk 처리 자체가 무거운데, 배치까지 동시에 열면 실행 시간과 실패 표면이 크게 늘어난다.
- 현재 UI/백엔드 구조에서 범위를 통제하는 편이 안전하다.

UI 문구 처리:

- 배치 + 자막 선택 시에는 "Whisper 로컬 생성은 우선 단일 영상 자막에서만 지원" 안내를 노출한다.

### 프론트엔드 수정 대상

- [`app/static/index.html`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\index.html)
  - 자막 방식 select
  - Whisper 모델 select
  - VAD checkbox
  - 도움말 텍스트
- [`app/static/app.js`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\app.js)
  - 필드 show/hide 로직
  - payload 직렬화
  - subtitle mode 상태 메시지 보강
- [`app/static/styles.css`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\styles.css)
  - 신규 필드 레이아웃 정리

## 백엔드 API 반영안

### 모델 확장

- [`app/models.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\models.py)

추가 예정 필드:

- `subtitle_engine: Literal["youtube", "whisper"] = "youtube"`
- `whisper_model: str = "base"`
- `vad_filter: bool = True`

적용 대상:

- `SubtitleRequest`
- `JobRequest`

검증 규칙:

- `subtitle_engine == "whisper"`일 때만 `whisper_model` 검증 강제
- `task_type == "batch"`이고 `batch_mode == "subtitle"`일 때 `subtitle_engine == "whisper"`는 1차 구현에서 거부

### 라우팅

- [`app/main.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\main.py)

변경 방향:

- 기존 `task_type == "subtitle"` 분기 내부에서
  - `subtitle_engine == "youtube"`면 기존 `extract_subtitles`
  - `subtitle_engine == "whisper"`면 새 `extract_whisper_subtitles`
- 동기 endpoint `/api/subtitles`도 동일하게 확장
- healthcheck 응답에 아래 정보를 추가하면 UI 동기화가 쉬워진다.
  - `subtitleEngines`
  - `whisperModels`

## 구현 예정 파일 목록

추가:

- [`extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\extractor.py)
- [`app/services/whisper_subtitle_extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\whisper_subtitle_extractor.py)
- [`tests/test_whisper_subtitle_extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\tests\test_whisper_subtitle_extractor.py)

수정:

- [`requirements.txt`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\requirements.txt)
- [`README.md`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\README.md)
- [`app/models.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\models.py)
- [`app/main.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\main.py)
- [`app/services/extractor.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\services\extractor.py)
- [`app/static/index.html`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\index.html)
- [`app/static/app.js`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\app.js)
- [`app/static/styles.css`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\app\static\styles.css)
- [`tests/test_api.py`](C:\Users\yhlee\Desktop\myprojects\Youtube_Audio_Extractror\tests\test_api.py)

## 테스트 계획

### 단위 테스트

- Whisper 모델명 검증
- SRT 렌더링 결과 검증
- chunk offset 병합 검증
- 긴 영상에서 chunk 분할 경로 선택 검증
- `vad_filter` 전달 검증
- 모델 미존재 시 오류 처리 검증

### API 테스트

- `subtitleEngine=whisper` payload 수용 여부
- `whisperModel`, `subtitleLanguage`, `vadFilter` 전달 여부
- 완료 후 `.srt` 다운로드 응답 확인
- 배치 + whisper subtitle 거부 검증

### CLI 테스트

- 필수 인자 누락 시 종료 코드 검증
- 정상 실행 시 성공 메시지/출력 경로 검증
- 잘못된 모델 입력 시 argparse 검증 확인

## 구현 순서

1. `faster-whisper` 상수/옵션 정의와 요청 모델 확장
2. Whisper 전용 서비스 모듈 추가
3. 기존 extractor 유틸에서 WAV 변환/분할 helper 정리
4. FastAPI 분기 연결
5. CLI `extractor.py` 추가
6. 웹 UI 필드 추가
7. 테스트 추가 및 문서 보완

## 구현 시 주의점

- 현재 자막 기능은 "YouTube 제공 자막"과 "로컬 생성 자막"이 성격이 다르다.
  - 같은 `subtitle` 모드에 묶되, 엔진 분기를 명확히 해야 한다.
- Windows 환경에서 긴 파일명, 임시 파일 정리, ffmpeg stderr decoding을 기존 패턴과 맞춘다.
- `large-v3-turbo`는 속도/성능이 좋지만 저사양 PC에서는 메모리와 시간이 크게 들 수 있다.
- 실제 오프라인 요구를 지키려면 모델 준비 상태를 명확히 다뤄야 한다.

## 승인 후 바로 진행할 구현 범위

- 단일 영상 기준 Whisper SRT 생성
- CLI `extractor.py`
- FastAPI subtitle 엔진 분기
- 웹 UI의 subtitle 모드 확장
- 테스트 추가

배치 Whisper 자막은 1차 범위에서 제외하고, 필요하면 다음 단계로 분리하는 것이 적절하다.
