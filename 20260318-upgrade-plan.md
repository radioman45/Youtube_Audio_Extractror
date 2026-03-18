# 2026-03-18 Upgrade Plan

## 진행 상태

- [x] 1단계 완료
- [ ] 2단계 미착수
- [ ] 3단계 미착수
- [ ] 4단계 미착수
- [ ] 5단계 미착수
- [ ] 6단계 미착수
- [ ] 7단계 미착수
- [ ] 8단계 미착수

## 목표

- [ ] 자막이 없는 YouTube 영상도 현재보다 빠르고 안정적으로 처리한다.
- [ ] 사용자는 엔진을 직접 고르지 않아도 URL만 넣고 자막 추출을 시작할 수 있어야 한다.
- [ ] 빠른 경로가 있으면 먼저 사용하고, 없으면 느린 전사 경로로 자동 전환한다.
- [ ] 실패 시 재시작 비용을 줄이고 긴 영상에서도 중단 복구가 쉬워야 한다.
- [ ] 장기적으로는 `notegpt.io`에 가까운 체감 속도를 낼 수 있는 구조를 만든다.

## 현재 분석 요약

- [x] 예시 영상 `jw_o0xr8MWU`는 2026-03-18 기준 `subtitles`와 `automatic_captions`가 모두 없다.
- [x] 현재 프로젝트는 YouTube 자막 다운로드와 Whisper 로컬 전사를 별도 엔진으로 분리해 두었다.
- [x] 기존 구조는 자막이 없을 때 자동 fallback이 없어 사용자가 직접 엔진을 바꿔야 했다.
- [x] Whisper URL 경로는 `전체 다운로드 -> 전체 WAV 변환 -> 모델 로드 -> chunk 전사` 구조라 긴 영상에서 느리고 실패 비용이 크다.
- [x] 현재 Colab 경로는 업로드 오디오 중심이라 URL 기반 빠른 전사 UX를 직접 해결하지 못한다.
- [x] `notegpt.io` 수준의 체감 속도를 내려면 로컬 Whisper 개선만으로는 부족하고 remote-capable 경로가 필요하다.

## 권장 방향

- [x] 기본 구조는 `caption-first + fallback`으로 재구성한다.
- [x] 1차 구현은 `YouTube captions -> local Whisper` 자동 전환부터 시작한다.
- [ ] 2차 구현은 자막 후보 탐색을 고도화해 "자막은 있지만 언어 선택이 빗나간" 실패를 줄인다.
- [ ] 3차 구현은 provider 구조로 바꿔 `Remote ASR`을 자연스럽게 끼워 넣는다.
- [ ] 최종 구조는 `YouTube captions -> Remote ASR -> Local Whisper`를 목표로 한다.

## ADR

### Decision

- [x] 자막 추출 구조를 단일 엔진 직접 선택 방식에서 자동 라우팅 방식으로 전환한다.

### Drivers

- [x] 자막이 없는 영상에서 사용자 수동 전환을 제거해야 한다.
- [x] 긴 영상에서 실패 시 재시작 비용을 줄여야 한다.
- [x] CPU-only 환경에서도 최소한 실패 없는 fallback은 보장해야 한다.
- [x] 빠른 UX를 만들려면 caption-first 접근이 가장 비용 대비 효과가 크다.

### Alternatives Considered

- [x] 로컬 Whisper만 계속 개선
- [x] 업로드 전용 Colab만 유지
- [x] Remote ASR 중심 구조로 전환

### Why Chosen

- [x] 현재 코드베이스를 크게 버리지 않으면서 UX를 바로 개선할 수 있다.
- [x] 빠른 caption 경로와 느린 transcription 경로를 하나의 사용자 흐름으로 묶을 수 있다.

### Consequences

- [x] 백엔드 라우팅 로직과 job 상태 관리가 조금 더 복잡해진다.
- [ ] remote backend 도입 시 비용, 운영, 보안 검토가 추가로 필요하다.

### Follow-ups

- [ ] remote backend 방식 결정
- [ ] Colab을 URL handoff 보조 경로로 쓸지 결정
- [ ] 개인정보/보안 정책 정리

## 단계별 체크리스트

### 1단계. `auto` 라우팅 추가

상태: 완료

- [x] `subtitle_engine`에 `auto` 값을 추가한다.
- [x] 기본 자막 엔진을 `youtube`/`whisper` 직접 선택이 아닌 `auto`로 변경한다.
- [x] `auto` 모드에서 YouTube 자막을 먼저 시도한다.
- [x] YouTube 자막이 없으면 Whisper 로컬 전사로 자동 fallback 한다.
- [x] 실제 사용 경로를 job details에 기록한다.
- [x] `resolvedSubtitleEngine`를 기록한다.
- [x] `resolvedSubtitlePath`를 기록한다.
- [x] 웹 UI 기본값을 `auto`로 바꾼다.
- [x] 데스크톱 UI 기본값을 `auto`로 바꾼다.
- [x] 사용자 안내 문구를 "먼저 YouTube 자막 확인, 없으면 Whisper" 기준으로 수정한다.
- [x] `/api/subtitles` 동기 경로도 `auto` fallback을 지원한다.
- [x] URL 기반 background job 재시작 로직이 `auto` 경로를 다시 이어받을 수 있게 정리한다.
- [x] 관련 API/UI 테스트를 추가 또는 수정한다.
- [x] 검증 완료: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_launcher.py tests/test_subtitle_extractor.py`

구현 반영 파일

- [x] `app/models.py`
- [x] `app/main.py`
- [x] `app/services/subtitle_extractor.py`
- [x] `app/services/whisper_subtitle_extractor.py`
- [x] `app/static/index.html`
- [x] `app/static/app.js`
- [x] `launcher.py`
- [x] `tests/test_api.py`
- [x] `tests/test_launcher.py`

### 2단계. 자막 후보 탐색 고도화

상태: 미착수

- [ ] `resolve_subtitle_track()`를 단일 exact match 중심에서 후보 우선순위 선택 구조로 바꾼다.
- [ ] 우선순위를 `exact match -> prefix match -> 같은 언어 계열 -> 자동 자막 후보 -> ASR fallback`으로 정리한다.
- [ ] "자막 트랙 자체가 없음"과 "요청 언어만 없음"을 구분한다.
- [ ] 언어 선택 때문에 불필요하게 Whisper로 내려가는 케이스를 줄인다.
- [ ] 관련 단위 테스트와 API 테스트를 보강한다.

대상 파일

- [ ] `app/services/subtitle_extractor.py`
- [ ] `tests/test_subtitle_extractor.py`
- [ ] `tests/test_api.py`

### 3단계. Subtitle Routing Service / Provider 추상화

상태: 미착수

- [ ] `YouTubeCaptionProvider`
- [ ] `RemoteAsrProvider`
- [ ] `LocalWhisperProvider`
- [ ] `app/main.py`의 직접 분기 로직을 provider 기반으로 옮긴다.
- [ ] 이후 remote backend 추가 시 UI/엔트리포인트를 다시 뜯지 않도록 만든다.

대상 파일

- [ ] `app/main.py`
- [ ] 신규 subtitle routing service 모듈
- [ ] `tests/test_api.py`

### 4단계. Local Whisper I/O 경량화

상태: 미착수

- [ ] `전체 다운로드 -> 전체 WAV 생성 -> chunk 분할` 구조를 줄인다.
- [ ] 가능하면 chunk 단위 또는 stream에 가까운 중간 처리로 바꾼다.
- [ ] 첫 결과가 더 빨리 나오도록 chunk 크기를 줄인다.
- [ ] 긴 영상/CPU 환경에서 체감 대기 시간을 낮춘다.

권장 기준

- [ ] 기본 chunk 목표를 5~10분대로 낮춘다.

대상 파일

- [ ] `app/services/extractor.py`
- [ ] `app/services/whisper_subtitle_extractor.py`
- [ ] `tests/test_whisper_subtitle_extractor.py`

### 5단계. Checkpoint / Resume 세분화

상태: 미착수

- [ ] checkpoint 단위를 현재 chunk 완료 기준보다 더 잘게 나눈다.
- [ ] 실패 시 마지막 30분 전체 재시작이 아니라 더 작은 단위만 재처리하게 만든다.
- [ ] job details에 진행률 관련 필드를 추가한다.
- [ ] `completedSeconds` 기록
- [ ] `lastCheckpointAt` 기록
- [ ] `estimatedRemainingSeconds` 기록

대상 파일

- [ ] `app/services/whisper_subtitle_extractor.py`
- [ ] `app/services/extraction_jobs.py`
- [ ] `tests/test_whisper_subtitle_extractor.py`
- [ ] `tests/test_api.py`

### 6단계. Chunk 경계 품질 보강

상태: 미착수

- [ ] chunk overlap을 2~5초 수준으로 도입한다.
- [ ] 병합 시 중복 구간을 텍스트/시간 기준으로 정리한다.
- [ ] 문장 경계가 chunk 사이에서 끊기는 문제를 줄인다.

대상 파일

- [ ] `app/services/whisper_subtitle_extractor.py`
- [ ] `tests/test_whisper_subtitle_extractor.py`

### 7단계. Remote ASR 경로 추가

상태: 미착수

- [ ] remote provider를 실제 동작 경로로 추가한다.
- [ ] 후보는 `자체 GPU worker`, `외부 전사 API`, `URL 기반 Colab handoff`다.
- [ ] 제품 목표가 `notegpt.io` 유사 UX라면 remote GPU 경로를 1순위로 둔다.
- [ ] remote 미구성 환경에서는 local Whisper fallback이 계속 동작해야 한다.

대상 파일

- [ ] `app/models.py`
- [ ] `app/main.py`
- [ ] 신규 remote service 모듈
- [ ] `app/static/index.html`
- [ ] `app/static/app.js`
- [ ] `launcher.py`
- [ ] 관련 테스트 일체

### 8단계. Colab URL Handoff 확장 여부 결정

상태: 미착수

- [ ] 업로드 전용 Colab handoff를 URL 기반 보조 경로로 확장할지 결정한다.
- [ ] 유지한다면 `auto` 라우팅에서 remote 미구성 시 추천/대체 경로로 연결한다.
- [ ] 독립 remote backend를 대체할 수준인지, 임시 보조 수단인지 명확히 정리한다.

대상 파일

- [ ] `app/main.py`
- [ ] `app/services/colab_transcription.py`
- [ ] `launcher.py`
- [ ] `docs/colab/README.md`
- [ ] 관련 테스트

## 수용 기준 체크리스트

- [x] 사용자는 URL만 입력하고 기본값 `auto`로 자막 추출을 시작할 수 있어야 한다.
- [x] YouTube 자막이 있으면 Whisper 없이 빠르게 종료되어야 한다.
- [x] YouTube 자막이 없으면 자동으로 Whisper 경로로 넘어가야 한다.
- [x] UI와 job details에서 실제 선택된 경로를 추적할 수 있어야 한다.
- [ ] 자막 언어 선택 실패 때문에 불필요한 Whisper fallback이 크게 줄어야 한다.
- [ ] 긴 Whisper 작업이 실패해도 재시작 비용이 chunk 전체보다 더 작아야 한다.
- [ ] chunk 경계에서 문장 손실이나 중복이 눈에 띄게 줄어야 한다.
- [ ] remote backend가 없는 환경에서도 local fallback은 항상 유지되어야 한다.
- [ ] remote backend가 있는 환경에서는 체감 속도가 현저히 개선되어야 한다.

## 검증 체크리스트

- [x] 단위/통합 테스트로 `auto` 라우팅을 검증했다.
- [x] API에서 `auto -> whisper fallback` 케이스를 검증했다.
- [x] background job에서 `resolvedSubtitleEngine` / `resolvedSubtitlePath` 기록을 검증했다.
- [x] launcher UI visibility를 검증했다.
- [ ] 자막 후보 우선순위 탐색 테스트
- [ ] checkpoint resume 세분화 테스트
- [ ] chunk overlap 병합 테스트
- [ ] remote 미구성 -> local fallback 테스트
- [ ] remote 구성 -> remote 우선 처리 테스트
- [ ] 수동 시나리오 검증
- [ ] 자막 있는 영상
- [ ] 자동 자막만 있는 영상
- [ ] 자막/자동 자막 모두 없는 영상
- [ ] 2시간 이상 긴 영상
- [ ] GPU 없는 PC

## 리스크와 대응

- [ ] Remote ASR 도입 시 비용이 증가할 수 있다.
- [ ] 대응: `caption-first` 우선으로 remote 호출량을 줄인다.
- [ ] 외부 전사 경로는 개인정보/보안 이슈가 생길 수 있다.
- [ ] 대응: local-only 모드를 유지하고 remote 사용 여부를 명시한다.
- [ ] YouTube 메타데이터 구조는 변동 가능성이 있다.
- [ ] 대응: caption 탐색 실패와 ASR fallback을 분리해 설계한다.
- [ ] Colab은 세션 안정성이 낮다.
- [ ] 대응: Colab은 보조 경로로만 취급한다.

## 구현 우선순위

- [x] 1. `auto` 라우팅
- [ ] 2. 자막 후보 탐색 고도화
- [ ] 3. local Whisper checkpoint/chunk 개선
- [ ] 4. remote ASR 또는 URL 기반 Colab 경로 추가
- [ ] 5. UI/desktop 진행 상태와 ETA 개선

## 최종 권고

- [x] 현재 목표에 가장 맞는 방향은 `caption-first + remote-capable fallback + hardened local fallback` 구조다.
- [x] 1단계만으로도 "자막이 없으면 사용자가 직접 엔진을 다시 고르는 문제"는 해소된다.
- [ ] 체감 속도를 `notegpt.io` 수준으로 끌어올리려면 7단계 remote ASR이 사실상 필요하다.
