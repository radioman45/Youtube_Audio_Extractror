# Colab GPU 전사 연동 계획

## 목표

- 업로드한 오디오 파일에 대해 선택 가능한 Colab 기반 전사 경로를 추가한다.
- 로컬 GPU가 없는 사용자에게 더 빠른 전사 속도와 더 높은 모델 품질 선택지를 제공한다.
- 현재 로컬 `faster-whisper` 경로는 기본 대체 경로로 유지한다.
- 이번 단계에서는 계획만 작성하고 구현은 하지 않는다.

## 결정 요약

- 권장 방향: 업로드 오디오 전용의 사용자 보조형 Colab handoff 워크플로를 추가한다.
- Google 로그인, Colab 런타임 시작, 브라우저 조작 자동화는 시도하지 않는다.
- 기존 로컬 Whisper 흐름은 그대로 유지하고 Colab을 두 번째 실행 경로로 추가한다.
- 노트북 내부 전사 엔진은 GPU `faster-whisper`를 기본으로 사용한다.
- `WhisperX` 정렬과 화자 분리는 1차 범위에서 제외한다.

## 이 방향을 권장하는 이유

- 현재 앱은 이미 업로드 오디오 -> 로컬 Whisper 전사 -> 결과 다운로드 흐름을 지원한다.
  - `app/main.py:323-355`
  - `app/main.py:503-572`
  - `app/services/whisper_subtitle_extractor.py:1499-1534`
- 현재 앱은 Whisper 작업 상세 정보, 진행률 추적, 재개 메타데이터를 이미 갖고 있다.
  - `app/main.py:99-123`
  - `app/main.py:360-409`
  - `app/services/whisper_subtitle_extractor.py:1269-1290`
- 무료 Colab GPU는 유용하지만 제품 기능으로 완전 자동화하기에는 안정성이 부족하다.
- handoff 방식은 깨지기 쉬운 브라우저 자동화를 피하면서도 GPU 기반 고속 전사 이점을 제공한다.

## 범위

- 포함:
  - 업로드 오디오 파일 전사만 지원
  - 웹 UI 흐름
  - FastAPI API 흐름
  - 같은 구조 안에서 가능하면 데스크톱 런처도 대응
  - Colab 노트북 템플릿과 import/export 산출물
  - 반환된 자막 파일과 작업 메타데이터 검증
- 제외:
  - Colab 안에서 YouTube URL 직접 실행
  - Google 계정 로그인 또는 노트북 실행 완전 자동화
  - 1차 범위에서 배치 자막 Colab 처리
  - 화자 분리, 단어 단위 정렬, 편집기 수준의 정밀 타임코드

## 현재 구조 요약

- 앱은 Whisper를 자막 엔진으로 노출하고 업로드 오디오 입력을 지원한다.
  - `app/static/app.js:247-257`
  - `app/static/app.js:427-445`
  - `app/static/index.html`
- 백엔드는 업로드된 원본 오디오를 저장하고 job을 만들고 백그라운드에서 로컬 Whisper를 실행한다.
  - `app/main.py:323-355`
  - `app/main.py:503-572`
- 로컬 Whisper 전사는 입력을 WAV로 변환하고, 모델을 로드하고, 긴 오디오를 청크로 나누고, resume 상태를 저장한다.
  - `app/services/whisper_subtitle_extractor.py:1208-1290`
  - `app/services/whisper_subtitle_extractor.py:1304-1417`
- 데스크톱 pause/resume은 현재 로컬 Whisper 작업에만 연결돼 있다.
  - `launcher.py:226-227`
  - `launcher.py:525`
  - `launcher.py:801-854`

## 제품 요구사항

- 사용자는 업로드한 오디오 파일 전사 시 로컬 Whisper와 Colab GPU 중 하나를 선택할 수 있어야 한다.
- 앱은 기존 로컬 경로를 깨지 않고 Colab 실행용 job package를 생성해야 한다.
- 앱은 사용자가 수동 실행할 수 있는 안정적인 노트북 링크 또는 노트북 산출물을 제공해야 한다.
- 노트북은 앱이 검증하고 가져올 수 있는 결과 패키지를 출력해야 한다.
- 앱은 유효하지 않거나 서로 맞지 않는 결과 패키지를 거부해야 한다.
- 앱은 Colab을 원하지 않는 사용자에게 현재 로컬 Whisper 흐름을 그대로 제공해야 한다.
- 앱은 아래 Colab 한계를 명확히 안내해야 한다.
  - 수동 단계가 필요함
  - 무료 GPU 가용성은 보장되지 않음
  - 런타임이 중간에 끊길 수 있음
  - 사용자가 Colab에 업로드하는 데이터의 프라이버시는 별도로 고려해야 함

## 권장 사용자 흐름

1. 사용자가 `subtitle` 모드, `whisper` 엔진, `audio_file` 소스, `colab` 실행 대상을 선택한다.
2. 사용자가 오디오 파일을 업로드한다.
3. 앱이 아래 정보를 포함한 Colab handoff job을 생성한다.
   - 원본 파일
   - 정규화된 job 메타데이터
   - 결과 검증 정보
   - 체크섬 또는 파일 지문
4. 앱이 아래 기능을 제공한다.
   - job bundle 다운로드
   - Colab 노트북 열기
   - 노트북 사용 안내 복사
5. 사용자가 Colab에서 노트북을 수동 실행한다.
6. 노트북이 아래 산출물을 만든다.
   - 자막 파일
   - 결과 manifest
   - 선택적 디버그 메타데이터
7. 사용자가 결과 패키지를 다시 앱에 가져온다.
8. 앱이 결과 패키지를 검증하고 job을 완료 상태로 바꾼다.

## 아키텍처 계획

### 1. 실행 대상 개념 추가

- 로컬 Whisper와 Colab Whisper가 함께 공존할 수 있도록 요청 모델을 확장한다.
- 권장 필드:
  - `whisper_runtime: Literal["local", "colab"] = "local"`
- 큰 라우팅 변경을 피하기 위해 `subtitle_engine="whisper"`는 그대로 유지한다.
- 영향 예상 파일:
  - `app/models.py`
  - `app/main.py`
  - `app/static/app.js`
  - `app/static/index.html`
  - `launcher.py`

### 2. Colab job 서비스 도입

- Colab용 패키징과 검증을 담당하는 새 서비스 모듈을 추가한다.
- 권장 새 파일:
  - `app/services/colab_transcription.py`
- 역할:
  - job manifest 생성
  - bundle zip 생성
  - 체크섬 계산 및 검증
  - 결과 manifest 스키마 정의
  - 가져온 결과 패키지 검증

### 3. 로컬 전사 서비스는 유지

- 현재 로컬 전사 함수 내부에 Colab 전용 로직을 섞지 않는다.
- 기존 로컬 `faster-whisper` 동작은 그대로 유지한다.
  - `app/services/whisper_subtitle_extractor.py`
- Colab 오케스트레이션은 현재 서비스를 대체하지 않고 바깥 계층에서 감싼다.

### 4. Colab 전용 API 엔드포인트 추가

- 권장 엔드포인트:
  - `POST /api/subtitles/upload/colab/jobs`
  - `GET /api/subtitles/colab/jobs/{job_id}/bundle`
  - `POST /api/subtitles/colab/jobs/{job_id}/complete`
  - `GET /api/subtitles/colab/notebook`
- 목적:
  - handoff job 생성
  - bundle zip 다운로드
  - 노트북 결과 가져오기
  - 노트북 템플릿 또는 노트북 URL 제공
- 기존 업로드 엔드포인트는 로컬 Whisper 용도로 유지한다.
  - `app/main.py:503-572`

### 5. bundle 형식 정의

- 권장 bundle 구성:
  - `source/uploaded-audio.<ext>`
  - `manifest.json`
  - `result-schema.json`
  - `README.txt`
- manifest 필드:
  - `jobId`
  - `sourceName`
  - `sourceSha256`
  - `language`
  - `subtitleFormat`
  - `preferredModel`
  - `qualityPreset`
  - `createdAt`
  - `appVersion`
- 결과 패키지 구성:
  - `result.srt` 또는 `result.txt`
  - `result.json`
  - 선택적 `segments.json`

### 6. 노트북 설계

- 노트북 템플릿을 저장소에 넣거나 다운로드 가능한 자산으로 제공한다.
- 권장 새 산출물:
  - `docs/colab/whisper_transcribe.ipynb`
- 노트북 동작:
  - 의존성 설치
  - 업로드된 bundle 또는 Drive 마운트 bundle 로드
  - 입력 manifest 검증
  - GPU `faster-whisper` 실행
  - 앱이 기대하는 형식으로 결과 zip 생성
- 권장 기본 모델 정책:
  - 속도 중심 GPU 실행은 `large-v3-turbo`
  - 품질 중심 프리셋은 `large-v3`
- 선택적 노트북 프리셋:
  - `speed`
  - `balanced`
  - `quality`

### 7. 웹 UI 변경

- 아래 조건에서만 보이는 runtime 선택 UI를 추가한다.
  - `taskType=subtitle`
  - `subtitleEngine=whisper`
  - `subtitleSource=audio_file`
- UI 추가 항목:
  - runtime 선택: `Local PC` 또는 `Google Colab GPU`
  - 노트북 안내 문구
  - `Create Colab Package` 버튼
  - `Open Colab Notebook` 버튼
  - `Import Colab Result` 버튼
- 영향 예상 파일:
  - `app/static/index.html`
  - `app/static/app.js`
  - `app/static/styles.css`

### 8. 데스크톱 런처 대응

- 데스크톱 런처에도 동일한 runtime 선택 UI를 추가한다.
- 1차 범위에서는 Colab job에 pause/resume을 제공하지 않는다.
- 데스크톱 Colab 흐름은 아래처럼 단순하게 유지한다.
  - package 내보내기
  - 노트북 링크 열기
  - 결과 가져오기
- 영향 예상 파일:
  - `launcher.py`
- `supports_pause_resume`는 로컬 runtime에만 적용되도록 유지한다.

### 9. job 상태 모델

- job store에 Colab 전용 상태를 명시적으로 추가한다.
- 권장 상태:
  - `queued`
  - `preparing_bundle`
  - `waiting_for_colab`
  - `importing_result`
  - `completed`
  - `failed`
- 추가 상세 정보:
  - `whisperRuntime`
  - `colabNotebookUrl`
  - `bundlePath`
  - `sourceSha256`
  - `resultImportedAt`
  - `resultModel`
  - `resultDurationSeconds`

### 10. 품질 정책

- 1차 범위에서는 추론 파라미터를 너무 많이 노출하지 않는다.
- 단순한 프리셋 기반으로 시작한다.
  - `speed` -> `large-v3-turbo`
  - `balanced` -> `large-v3-turbo`
  - `quality` -> `large-v3`
- 출력 형식은 현재 앱 동작과 맞춘다.
  - `timestamped` -> `.srt`
  - `clean` -> `.txt`
- 아래 점을 명확히 안내한다.
  - Colab 품질은 선택한 모델에 따라 달라짐
  - GPU 가용성에 따라 처리 시간이 달라짐
  - 노트북 실행이 정상 종료돼야 결과를 가져올 수 있음

## 인수 기준

- 사용자는 업로드 오디오 파일로 Colab handoff job을 생성할 수 있어야 하며, 기존 로컬 업로드 Whisper 흐름은 깨지지 않아야 한다.
- 앱은 오디오와 manifest 메타데이터를 포함한 유효한 bundle zip을 생성할 수 있어야 한다.
- 앱은 유효한 Colab 결과 패키지를 가져와 job을 완료 처리할 수 있어야 한다.
- 앱은 아래 경우를 거부해야 한다.
  - 잘못된 job id
  - 잘못된 체크섬
  - 누락된 자막 출력
  - 유효하지 않은 manifest
- `whisper_runtime="local"`일 때 기존 로컬 Whisper job은 그대로 동작해야 한다.
- 데스크톱과 웹 UI 모두 Colab이 수동 외부 단계라는 점을 안내해야 한다.
- 1차 범위에서 Colab job은 pause/resume 지원을 표시하지 않아야 한다.

## 구현 단계 계획

### 1단계. 모델과 API 계약 정리

- `app/models.py`에 `whisper_runtime`을 추가한다.
- 프론트엔드가 runtime 선택지를 렌더링할 수 있도록 `app/main.py`의 config 메타데이터 응답을 확장한다.
- Colab은 업로드 오디오 + Whisper 자막 job에서만 허용되도록 백엔드 검증을 추가한다.

### 2단계. Colab job 패키징 서비스

- `app/services/colab_transcription.py`를 추가한다.
- bundle 생성, manifest 직렬화, 체크섬 생성, 결과 검증을 구현한다.
- 이 로직은 로컬 `whisper_subtitle_extractor.py`와 분리한다.

### 3단계. 백엔드 엔드포인트

- `app/main.py`에 Colab job 생성 및 완료 엔드포인트를 추가한다.
- 기존 job store 패턴을 재사용해 상태 업데이트와 결과 다운로드 연결을 처리한다.
- 앱 재시작 후에도 안전하게 복구할 수 있도록 필요한 메타데이터를 저장한다.

### 4단계. 노트북 산출물

- `docs/colab/` 아래에 Colab 노트북 템플릿을 추가한다.
- 노트북과 앱 사이의 안정적인 결과 패키지 계약을 정의한다.
- 단순한 사용 방법과 모델 프리셋 선택지를 포함한다.

### 5단계. 웹 UI

- `app/static/index.html`에 runtime 선택과 Colab 전용 액션을 추가한다.
- `app/static/app.js`의 표시/숨김 로직과 제출 흐름을 갱신한다.
- 수동 handoff와 프라이버시 유의사항을 설명하는 helper 문구를 추가한다.

### 6단계. 데스크톱 런처

- `launcher.py`에 runtime 선택을 반영한다.
- 데스크톱 사용자도 export/import 흐름을 사용할 수 있게 한다.
- pause/resume은 로컬 Whisper job에만 유지한다.

### 7단계. 테스트

- 아래 API 테스트를 추가한다.
  - Colab job 생성
  - bundle 다운로드
  - 유효한 결과 가져오기
  - 잘못된 결과 거부
- `whisper_runtime` 모델 검증 테스트를 추가한다.
- 가능하면 runtime 선택 UI 노출 조건 테스트를 추가한다.

### 8단계. 문서화

- `README.md`를 갱신한다.
- `docs/colab/README.md`에 아래 내용을 정리한다.
  - 사전 준비사항
  - 노트북 사용 방법
  - 제한사항
  - 프라이버시 경고
  - 실패 시 복구 절차

## 리스크와 대응

- 리스크: Colab 무료 GPU를 사용할 수 없는 시점이 있다.
  - 대응: 로컬 runtime을 항상 fallback으로 유지하고 Colab은 선택 기능으로만 제공한다.
- 리스크: 사용자가 완전 자동화를 기대한다.
  - 대응: UI와 문서에 수동 handoff 기능임을 명확히 표시한다.
- 리스크: 큰 오디오 파일의 Colab 업로드가 병목이 된다.
  - 대응: 이미 업로드된 소스 파일 기준으로 bundle을 만들고, 이후 단계에서 필요하면 압축 가이드를 추가 검토한다.
- 리스크: 결과 import가 위조되거나 다른 작업과 섞인다.
  - 대응: 결과 수락 전에 job id, source checksum, manifest 스키마를 모두 검증한다.
- 리스크: Colab 세션이 완료 전에 끊긴다.
  - 대응: 노트북은 결과를 zip 산출물로 저장해야 하고, 앱은 import 전까지 job을 `waiting_for_colab` 상태로 유지한다.
- 리스크: 데스크톱과 웹 흐름이 달라진다.
  - 대응: 두 클라이언트가 동일한 bundle/result 계약을 쓰도록 유지한다.

## 검증 계획

- 단위 테스트:
  - manifest 생성
  - 체크섬 검증
  - 결과 패키지 검증
  - 요청 모델 검증
- 통합 테스트:
  - Colab job 생성 -> bundle 다운로드 -> 결과 import
  - 잘못된 결과 패키지 거부
  - 로컬 runtime 기존 동작 유지
- 수동 검증:
  - 샘플 오디오 업로드
  - bundle 생성
  - Colab에서 노트북 수동 실행
  - 결과 import
  - 자막 파일 다운로드
- 회귀 검증:
  - 현재 로컬 업로드 Whisper 경로 정상 동작
  - 현재 URL 기반 Whisper 경로 정상 동작
  - 현재 데스크톱 로컬 Whisper pause/resume 정상 동작

## 1차 범위 비목표

- Colab 내부 자동 실행
- Google Drive 자동 동기화
- 배치 Colab 전사
- Colab 내부 YouTube URL 직접 전사
- WhisperX 정렬 및 화자 분리
- Colab 런타임 상태 백그라운드 polling

## ADR

- 결정:
  - 업로드 오디오 기반 Whisper 자막 전사에 대해 수동 handoff 방식의 Colab 선택 runtime을 추가한다.
- 결정 요인:
  - 로컬 GPU 없는 사용자의 속도 개선
  - 기존 로컬 구조 보존
  - 깨지기 쉬운 브라우저 자동화 회피
- 검토한 대안:
  - 로컬 runtime을 Colab으로 완전히 대체
  - Colab UI 자동 조작
  - 클라우드 옵션 없이 로컬만 유지
- 이 안을 선택한 이유:
  - 현재 로컬 경로를 깨지 않으면서도 실질적인 속도 개선 선택지를 제공할 수 있기 때문이다.
- 결과:
  - 사용자는 더 빠른 선택지를 얻지만 수동 노트북 실행 단계가 추가된다.
  - 백엔드 복잡도는 중간 정도 증가한다.
  - local과 colab의 pause/resume 의미는 서로 다르게 유지된다.
- 후속 과제:
  - 추후 Drive 기반 반자동 흐름 검토
  - CPU-only 사용자용 `whisper.cpp` 별도 검토
  - 대표적인 한국어 음성 샘플 기준 속도/품질 벤치마크 수행

