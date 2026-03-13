# 초보 학습 메모

> 목적: 이 프로젝트를 처음 보는 초보 개발자가 구조를 빠르게 이해하고, 같은 기능을 다시 추가하거나 유지보수할 때 참고할 수 있는 개인 학습 문서

---

## 1. 프로젝트를 한 줄로 설명하면

이 앱은 YouTube 링크나 오디오 파일을 입력받아 `yt-dlp`, `ffmpeg`, `faster-whisper`, FastAPI, 브라우저 UI를 조합해 오디오, 영상, 자막을 로컬에서 추출하는 도구다.

핵심 흐름은 아래와 같다.

1. 브라우저 UI에서 작업 요청
2. FastAPI가 요청 검증 후 백그라운드 작업 생성
3. 서비스 레이어가 `yt-dlp` 또는 업로드 파일을 처리
4. `ffmpeg`로 필요한 포맷으로 변환
5. 필요 시 `faster-whisper`로 전사
6. 결과 파일을 다운로드로 제공

---

## 2. 이번 작업에서 실제로 추가된 큰 기능

### 2.1 Whisper 로컬 자막 생성

- YouTube URL에서 음성을 내려받아 Whisper로 SRT 생성
- OpenAI API 없이 전부 로컬 실행
- 지원 모델:
  - `tiny`
  - `base`
  - `small`
  - `medium`
  - `large`
  - `large-v3`
  - `large-v3-turbo`

### 2.2 오디오 파일 업로드 후 전사

- 이미 가지고 있는 `mp3`, `wav`, `m4a`, `aac`, `opus`, `webm`, `flac` 같은 파일을 업로드해서 바로 자막 생성 가능
- 이 경우 `yt-dlp` 단계는 건너뛰고 `ffmpeg -> Whisper -> SRT`만 수행

### 2.3 긴 영상 처리용 chunk 전사

- 3시간, 4시간짜리 긴 영상은 한 번에 처리하면 메모리와 시간이 너무 많이 든다
- 그래서 WAV를 일정 길이로 나누고 chunk별로 Whisper 전사
- 나중에 각 chunk의 자막 시간을 다시 합쳐서 최종 SRT 생성

### 2.4 중간 저장과 재개

- Whisper 작업 중 완료된 chunk 결과를 JSON으로 저장
- 앱이 꺼지거나 브라우저가 닫혀도 다시 켜면 이어서 복구 가능
- 브라우저는 `localStorage`에 현재 작업 ID를 저장해서 자동 재연결

---

## 3. 어떤 파일을 보면 되는가

### 백엔드 진입점

- `app/main.py`
  - FastAPI 엔드포인트
  - 작업 생성
  - 백그라운드 스레드 실행
  - 앱 재시작 시 복구 트리거

### 요청 검증

- `app/models.py`
  - Pydantic 모델
  - task type, subtitle engine, whisper model, time range 검증

### 핵심 서비스

- `app/services/extractor.py`
  - 공통 다운로드, ffmpeg, yt-dlp 유틸
- `app/services/subtitle_extractor.py`
  - YouTube 자막 다운로드 방식
- `app/services/whisper_subtitle_extractor.py`
  - Whisper 자막 생성 핵심 로직
  - WAV 변환
  - chunk 분할
  - 모델 로드
  - SRT 렌더링
  - 중간 저장과 재개
- `app/services/extraction_jobs.py`
  - 작업 상태 저장
  - 진행률, 완료, 실패, JSON 영속화
- `app/services/app_state.py`
  - 앱 상태 폴더 위치 관리
  - 작업별 상태 폴더, work 폴더 경로 관리

### 프론트엔드

- `app/static/index.html`
  - 자막 방식, Whisper 모델, 입력 소스 UI
- `app/static/app.js`
  - 폼 전송
  - 진행률 폴링
  - 브라우저 재연결
  - 업로드 모드 분기
- `app/static/styles.css`
  - UI 스타일

### 배포

- `build_exe.ps1`
  - PyInstaller 빌드
- `launcher.py`
  - exe 실행 시 로컬 서버 시작과 브라우저 오픈

---

## 4. Whisper 기능의 실제 처리 순서

### YouTube URL 입력 시

1. URL 검증
2. `yt-dlp`로 원본 오디오 다운로드
3. `ffmpeg`로 Whisper 입력용 WAV 생성
4. 길면 chunk 분할
5. `faster-whisper` 전사
6. chunk 결과를 합쳐 `.srt` 생성

### 오디오 파일 업로드 시

1. 파일 확장자 검증
2. 업로드 파일을 작업용 폴더에 저장
3. `ffmpeg`로 WAV 변환
4. 길면 chunk 분할
5. `faster-whisper` 전사
6. `.srt` 생성

---

## 5. 왜 `base` 모델을 기본값으로 잡았는가

실전에서 중요한 건 “가장 좋은 품질”보다 “완료 가능한 속도와 안정성”이다.

- `large-v3-turbo`
  - 품질은 좋지만 CPU 환경에서 긴 영상에 너무 무겁다
  - 몇 시간짜리 영상은 대기 시간이 길고 중간 장애 리스크가 커진다
- `base`
  - 긴 영상도 상대적으로 안정적
  - 테스트와 실사용 균형이 가장 좋았다
- `small`
  - `base`보다 조금 느리지만 품질을 조금 더 챙기고 싶을 때 적당

현재 추천은 아래와 같다.

- 긴 영상: `base`
- 균형형: `small`
- 고사양 PC: `large-v3-turbo`

---

## 6. 이번에 실제로 겪은 에러와 원인

### 6.1 `faster-whisper is not installed`

원인:

- 전역 Python에는 패키지가 있었지만 `.venv`에는 없었다
- exe 빌드는 `.venv` 기준이라 실행 파일 안에서는 import 실패

해결:

- `.venv`에 `faster-whisper`와 관련 의존성 설치
- 다시 exe 빌드

교훈:

- “내 컴퓨터에서 import 된다”와 “빌드 환경에서 import 된다”는 다르다

### 6.2 `Whisper model 'large-v3-turbo' is not available locally`

원인:

- 처음에는 Whisper 모델을 로컬 캐시 전용으로만 찾도록 짰다
- 캐시가 없으면 오프라인 실패

해결:

- 먼저 로컬 캐시 확인
- 없으면 1회 다운로드
- 이후에는 로컬 캐시 재사용

교훈:

- “오프라인 실행”을 목표로 해도 최초 캐시 준비 흐름은 별도로 설계해야 한다

### 6.3 모델 다운로드 실패

원인:

- 허브 기본 다운로드 경로에서 `model.bin`이 끝까지 받아지지 않는 경우가 있었다

해결:

- 허브 로드 실패 시 앱 전용 캐시 폴더로 직접 다운로드하는 폴백 추가

교훈:

- 외부 라이브러리 기본 경로 하나만 믿으면 배포 환경에서 흔들린다

### 6.4 `An unexpected error occurred`

원인:

- 실제 내부 원인은 GPU 런타임 문제였다
- `cublas64_12.dll`이 없는 PC인데 GPU 경로를 타며 실패
- 예외가 일반 오류로 뭉개져 원인이 안 보였다

해결:

- Whisper 기본 장치를 `cpu`로 변경
- CUDA 관련 예외를 명시적인 런타임 에러로 변환

교훈:

- 사용자 PC 환경이 제각각이면 GPU보다 CPU 기본값이 더 안전할 수 있다

### 6.5 진행률이 91%에서 오래 멈춰 보임

원인:

- chunk 단위로만 진행률을 올렸기 때문에 chunk 내부 진행이 안 보였다

해결:

- Whisper 세그먼트가 나올 때마다 chunk 내부 퍼센트를 반영하도록 수정

교훈:

- 실제로 작업 중이어도 “멈춘 것처럼 보이는 UI”는 장애처럼 느껴진다

### 6.6 `Failed to fetch`

원인:

- 브라우저가 FastAPI 서버에 폴링 중이었는데, 앱 프로세스가 사라져 연결이 끊겼다
- 이건 Whisper 전사 오류가 아니라 브라우저와 로컬 서버 연결 문제였다

해결:

- 브라우저가 재연결을 반복 시도하게 수정
- 작업 ID를 저장해 앱 재시작 후 자동 복구
- 백엔드 작업 상태도 디스크에 저장

교훈:

- 프론트의 네트워크 에러와 백엔드 작업 실패는 분리해서 봐야 한다

---

## 7. 왜 작업 상태를 메모리만이 아니라 파일에도 저장했는가

처음에는 job 상태가 메모리에만 있었다. 이 경우 앱이 꺼지면 아래 문제가 생긴다.

- 진행 중인 작업이 사라짐
- 브라우저는 `Failed to fetch`만 보게 됨
- 이미 끝난 chunk도 다시 돌려야 함

그래서 아래 방향으로 바꿨다.

- 작업 상태를 `job.json`에 저장
- 작업별 work 디렉터리 유지
- Whisper 완료 chunk 목록 저장
- chunk 자막 JSON 저장
- 브라우저는 현재 active job ID 저장

이 구조의 장점:

- 앱 재시작 후 복구 가능
- 긴 작업이 훨씬 현실적
- 디버깅할 때 남은 중간 산출물로 원인 분석 가능

---

## 8. UI에 어떻게 붙였는가

자막 탭 안에서 아래 두 축으로 분기했다.

### 자막 방식

- `YouTube 자막 다운로드`
- `Whisper 로컬 생성`

### Whisper 입력 소스

- `YouTube URL`
- `오디오 파일 업로드`

이 구조가 좋은 이유:

- 기존 자막 기능을 유지할 수 있다
- 새로운 Whisper 기능을 한 탭 안에 자연스럽게 넣을 수 있다
- 사용자는 “자막을 어디서 만들지”와 “소스를 어디서 가져올지”를 분리해서 이해할 수 있다

---

## 9. 초보 입장에서 배울 수 있는 핵심 설계 포인트

### 9.1 service 레이어 분리는 유지보수 비용을 줄인다

`main.py`에 다운로드, ffmpeg, Whisper, 자막 렌더링을 다 넣지 않고 서비스 파일로 분리해 두면 에러 위치를 찾기 쉽다.

### 9.2 입력 검증은 엔드포인트보다 모델 쪽이 낫다

URL, 시간 형식, model name, subtitle engine을 `models.py`에서 먼저 걸러 주면 API 코드가 훨씬 단순해진다.

### 9.3 긴 작업은 동기 요청보다 job 기반이 낫다

Whisper처럼 오래 걸리는 작업은 즉시 응답보다 “작업 생성 -> 상태 조회 -> 다운로드” 구조가 맞다.

### 9.4 장애를 없애는 것만큼, 원인을 보이게 하는 것도 중요하다

이번 작업에서 가장 오래 걸린 부분은 “실패”보다 “왜 실패했는지 안 보이는 상태”였다.

좋은 예:

- CUDA 에러를 명시적인 문장으로 바꿈
- 모델 다운로드 실패를 일반 예외가 아닌 설명 가능한 메시지로 바꿈
- 브라우저 연결 실패와 Whisper 실패를 분리해서 다룸

### 9.5 배포 환경은 개발 환경과 다르다

- `.venv` 의존성 누락
- exe 잠금 문제
- PC마다 다른 GPU 런타임

이런 문제는 로컬 Python 실행만으로는 다 발견되지 않는다.

---

## 10. 앞으로 비슷한 기능을 추가할 때 추천 순서

1. 서비스 함수부터 콘솔에서 단독 실행
2. Pydantic 검증 추가
3. FastAPI 엔드포인트 연결
4. job store와 진행률 설계
5. UI 연결
6. 테스트 추가
7. exe 재빌드

이 순서를 지키면 어디가 깨졌는지 분리하기 쉽다.

---

## 11. 지금 상태에서 실사용 팁

- 긴 영상 Whisper는 먼저 `base`로 시도하는 것이 안전
- `large-v3-turbo`는 CPU에서 시간이 매우 오래 걸릴 수 있음
- 앱을 재빌드할 때는 실행 중인 `YouTubeAudioExtractorDesktop.exe`를 먼저 종료해야 함
- `Failed to fetch`가 보여도 바로 Whisper 실패라고 단정하면 안 됨
- 중간 산출물이 남아 있으면 temp/work 폴더를 먼저 확인하면 원인 분석이 쉬움

---

## 12. 다음에 개선하면 좋은 것

- chunk별 결과를 더 눈에 띄게 보여주는 UI
- 로그 파일 분리
- 취소 버튼
- 업로드 파일 drag & drop
- 재개 가능한 작업 목록 화면
- CPU/GPU 선택 UI

---

## 13. 한 줄 정리

이번 작업의 핵심은 “Whisper 기능 추가” 자체보다, 긴 로컬 전사 작업을 실제 사용 가능한 수준으로 만들기 위해 다운로드, 모델 캐시, 진행률, 오류 메시지, 중간 저장, 재연결 복구까지 함께 설계한 점이다.

---

## 14. 이번 마무리 작업에서 추가로 배운 것

### 14.1 지금 이 앱의 실제 실행 구조

처음에는 브라우저를 열어 `localhost` 페이지를 붙잡는 방식이었지만, 현재 사용 기준 실행 진입점은 `PySide6` 기반 데스크톱 런처다.

- 올바른 실행 파일: `dist/YouTubeAudioExtractorDesktop/YouTubeAudioExtractorDesktop.exe`
- 바탕화면 바로가기:
  - `YouTube Audio Extractor Desktop.lnk`
  - `YouTube Audio Extractor.lnk`

초보 입장에서 중요한 점은 “지금 어떤 실행 파일이 최신 산출물인지”를 구분하는 것이다. 같은 `dist` 폴더 아래에 예전 빌드가 남아 있으면, 코드가 아니라 잘못된 실행 파일 때문에 전혀 다른 증상이 보일 수 있다.

### 14.2 `This page is protected`는 Whisper 에러가 아니었다

사용자 입장에서는 자막 생성 버튼을 눌렀을 때 보호 페이지가 뜨니 Whisper가 깨진 것처럼 보일 수 있었다. 하지만 실제 원인은 구형 웹 런처가 `localhost`를 다시 띄우고 있었기 때문이다.

즉, “보이는 현상”과 “실제 실패 지점”이 다를 수 있다.

- 보호 페이지: 실행 진입점 문제
- 모델 다운로드 실패: 네트워크/모델 캐시 문제

이 둘을 분리해서 봐야 디버깅이 빨라진다.

### 14.3 회사망에서는 모델 다운로드 자체보다 인증서와 차단 정책이 먼저 문제였다

이번에 `Whisper model 'base' could not be downloaded`를 재현해 보니, 핵심 원인은 아래 두 가지였다.

1. `huggingface.co`가 회사/보안 네트워크에서 차단되어 `Website Blocking` HTML이 내려옴
2. 수동 fallback 코드가 `preprocessor_config.json`까지 필수라고 가정하고 있어, 실제 모델 저장소와 맞지 않는 경우 실패함

여기서 배운 점:

- 모델 다운로드 실패는 단순히 “인터넷이 안 됨”으로 뭉뚱그리면 안 된다.
- TLS 인증서 검증, 프록시, 보안 차단, 저장소 파일 구성 차이를 따로 봐야 한다.

### 14.4 최종 대응 방식

지금 Whisper 모델 준비 경로는 아래처럼 바뀌었다.

1. 로컬 캐시에 이미 모델이 있는지 확인
2. 없으면 공식 Hugging Face 경로를 시도
3. 공식 경로가 막히면 대체 미러로 재시도
4. TLS는 Windows 신뢰 저장소를 우선 사용
5. 내려받은 파일 중 실제 필수 파일만 검사
6. 성공 시 로컬 캐시에 저장해 다음부터 재사용

이 구조 덕분에 첫 다운로드만 통과하면 이후에는 오프라인에 가까운 방식으로 사용할 수 있다.

### 14.5 실사용 체크포인트

- Whisper `base` 모델 캐시는 `C:\\Users\\sv61529\\AppData\\Local\\YouTubeAudioExtractor\\whisper-models\\base`에 저장된다.
- 지금 사용자 PC에는 `base` 모델을 실제로 미리 받아 둔 상태다.
- 따라서 같은 사용자 계정에서 최신 `YouTubeAudioExtractorDesktop.exe`를 실행하면, 첫 자막 생성에서 다시 모델 다운로드 에러가 날 가능성은 크게 줄었다.

### 14.6 초보 관점에서 얻은 운영 교훈

- 배포물은 “소스가 맞다”보다 “사용자가 어떤 실행 파일을 눌렀는가”가 더 중요할 때가 있다.
- 외부 모델 의존 기능은 코드보다 네트워크 정책이 먼저 깨질 수 있다.
- 에러 메시지는 사용자 행동을 바꿀 수 있을 정도로 구체적이어야 한다.
- 문서에는 기능 설명뿐 아니라 “어떤 산출물을 실행해야 하는지”까지 적어 두는 편이 낫다.

---

## 15. 오늘 작업 추가 메모 (2026-03-13)

### 15.1 자막 형식 선택 추가

- 이제 자막 추출 시 2가지 형식을 선택할 수 있다.
  - `timestamped`: 타임스탬프가 포함된 `.srt`
  - `clean`: 시간 정보 없이 텍스트만 있는 `.txt`
- 초보자 기준 사용법:
  - 영상 편집이나 자막 플레이어용이면 `timestamped`
  - 요약, 복사/붙여넣기, 문서 정리용이면 `clean`

관련 파일:

- `app/services/subtitle_extractor.py`
- `app/services/whisper_subtitle_extractor.py`
- `app/main.py`
- `launcher.py`
- `app/static/index.html`
- `app/static/app.js`

### 15.2 Whisper 자막 추출 일시정지 / 재개

- Whisper 자막 추출 작업에 `일시정지` / `재개` 버튼을 추가했다.
- 동작 방식은 “강제 중단”이 아니라 “안전한 체크 지점에서 잠시 멈춤”이다.
- 즉, 버튼을 눌렀다고 0.1초 만에 딱 멈추는 것은 아니고:
  - 현재 처리 중인 세그먼트
  - 현재 내려받는 파일 조각
  - 현재 전사 중인 청크
  가 끝나는 시점에 멈춘다.

초보자 포인트:

- 이런 방식이 필요한 이유는 Whisper나 다운로드 작업은 중간에 억지로 끊으면 상태가 꼬일 수 있기 때문이다.
- 그래서 “바로 멈춤”보다 “안전하게 멈춤”이 더 중요하다.

핵심 파일:

- `app/services/task_control.py`
- `app/services/whisper_subtitle_extractor.py`
- `launcher.py`

### 15.3 Whisper 실행 장치 선택 추가

- 이제 Whisper 실행 장치를 직접 선택할 수 있다.
- 선택지는 3개다.
  - `Auto (GPU first, else CPU)`
  - `CPU only`
  - `NVIDIA GPU (CUDA)`

### 15.4 Auto 모드가 실제로 하는 일

`Auto`는 내부에서 아래 순서로 판단한다.

1. NVIDIA GPU(CUDA)를 사용할 수 있는지 확인
2. 가능하면 GPU로 Whisper 실행
3. GPU가 없으면 CPU로 실행
4. GPU가 있다고 판단했더라도 실제 실행 중 CUDA 라이브러리 문제가 나면 CPU로 자동 fallback

즉:

- 집 노트북처럼 NVIDIA GPU가 있는 PC는 보통 GPU 사용
- 회사 PC처럼 GPU가 없거나 제한된 PC는 CPU 사용

### 15.5 초보자에게 권장하는 선택

- 집 노트북(RTX 3050 등 NVIDIA GPU 있음): `Auto`
- 회사 PC(GPU 없음 또는 보안 정책으로 CUDA 사용 어려움): `Auto` 또는 `CPU only`
- `NVIDIA GPU (CUDA)`:
  - GPU 사용을 강제로 시도하는 옵션
  - CUDA 런타임/드라이버가 안 맞으면 실패할 수 있다.

실무적으로는 대부분 `Auto`가 가장 편하다.

### 15.6 왜 이번 수정이 중요한가

이전에는 Whisper가 사실상 CPU 경로로만 동작해서, GPU가 있어도 속도가 충분히 나오지 않을 수 있었다.

이번 수정으로:

- 고사양 PC에서는 GPU를 활용할 수 있고
- GPU가 없는 PC에서는 CPU로 안전하게 내려가며
- 같은 exe를 집/회사 PC에서 모두 사용할 수 있게 됐다.

### 15.7 파일을 따라가며 이해하는 순서

아래 순서대로 보면 구조를 이해하기 쉽다.

1. `launcher.py`
   - 데스크톱 화면에 `Whisper device` 선택 UI가 어디에 붙었는지 본다.
2. `app/models.py`
   - `whisper_device` 필드가 요청 모델에 어떻게 추가됐는지 본다.
3. `app/main.py`
   - API 요청값이 실제 Whisper 옵션으로 어떻게 전달되는지 본다.
4. `app/services/whisper_subtitle_extractor.py`
   - `auto -> cuda/cpu 선택 -> fallback`이 실제로 어떻게 동작하는지 본다.

### 15.8 오늘 수정 후 확인할 것

exe 실행 후 `자막 추출 -> Whisper`에서 아래를 확인하면 된다.

- `자막 형식`
  - `타임스탬프 포함 (.srt)`
  - `텍스트만 (.txt)`
- `Whisper 모델`
- `Whisper device`
  - `Auto (GPU first, else CPU)`
  - `CPU only`
  - `NVIDIA GPU (CUDA)`
- 작업 중
  - `일시정지`
  - `재개`

### 15.9 테스트 결과

오늘 수정 후 전체 테스트 결과:

- `66 passed`

이 의미는:

- Whisper 관련 기능
- API 연결
- 데스크톱 런처 연결
- 기존 자막 기능

이 다시 한 번 자동 확인되었다는 뜻이다.

---

## 16. 오늘 세션 추가 메모 (2026-03-13, Colab handoff 확장)

### 16.1 Colab handoff가 왜 필요한가

- 로컬 PC에 GPU가 없으면 긴 오디오 Whisper 전사가 매우 오래 걸릴 수 있다.
- 그래서 업로드한 오디오 파일만 Google Colab으로 넘겨 GPU에서 전사하고, 결과만 다시 앱으로 가져오는 수동 handoff 흐름을 추가했다.
- 중요한 점은 YouTube URL 전체를 Colab으로 보내는 구조가 아니라, 앱에서 준비한 오디오 파일 기준으로 번들 ZIP을 만들고 Colab에서 그것만 처리한다는 것이다.

### 16.2 이번에 추가된 Colab handoff 흐름

이제 업로드 Whisper 자막 작업에서는 `Whisper runtime`을 아래 두 가지 중에서 고를 수 있다.

- `Local PC`
- `Google Colab handoff`

`Google Colab handoff`를 고르면 작업 시작 버튼이 일반 전사 실행이 아니라 `Colab 패키지 만들기`로 바뀐다.

실행 순서는 아래와 같다.

1. 앱에서 Colab 번들 ZIP 생성
2. 번들 ZIP 저장
3. Colab 노트북 저장
4. Colab에서 노트북 실행
5. 번들 ZIP 업로드 또는 Google Drive 경로 사용
6. 전사 완료 후 `colab-result.zip` 생성
7. 앱에서 결과 ZIP 가져오기

### 16.3 패키지 안에는 무엇이 들어 있는가

Colab 번들 ZIP에는 아래 정보가 들어 있다.

- 원본 오디오 파일
- `manifest.json`
- 결과 검증용 스키마
- 간단한 안내 문서

`manifest.json`에는 job ID, 원본 파일 해시, 언어, 모델, 자막 형식 같은 정보가 들어 있고, Colab 결과를 다시 가져올 때 이 값을 이용해 다른 파일이 섞이지 않았는지 검증한다.

즉, Colab handoff는 “그냥 ZIP 하나 올리고 결과 ZIP 하나 받는 단순 작업”처럼 보여도 내부적으로는 원본 일치 여부를 확인하는 안전장치가 있다.

### 16.4 브라우저 UI와 데스크톱 UI가 둘 다 바뀌었다

이번 세션에서는 Colab handoff를 웹 UI와 데스크톱 런처 둘 다 연결했다.

- 웹 UI
  - Colab 패널 추가
  - 번들 다운로드
  - 노트북 다운로드
  - Colab 열기
  - 결과 ZIP import
- 데스크톱 UI
  - `Whisper runtime` 선택 추가
  - Colab 액션 버튼 추가
  - 결과 ZIP 가져오기 지원

즉, 같은 기능을 브라우저와 exe 런처 양쪽에서 모두 사용할 수 있게 만든 것이다.

### 16.5 작은 화면에서 메뉴가 안 보이던 문제

데스크톱 런처는 처음에 가로폭이 좁아지면 버튼과 라벨이 잘리거나 한 줄에 몰려서 보기 어려운 문제가 있었다.

이번 수정으로 아래처럼 바뀌었다.

- 창 폭이 작아지면 입력 행이 세로 배치로 전환
- 버튼 줄도 폭에 따라 세로 스택
- 상단 바도 좁아지면 줄바꿈
- 전체 화면을 스크롤 가능하게 처리

초보 관점에서 중요한 이유는 “기능이 없어서 안 보이는 것”과 “창이 좁아서 안 보이는 것”을 구분해야 하기 때문이다.

### 16.6 `?` 도움말 버튼을 왜 넣었는가

Colab handoff는 일반 다운로드보다 단계가 많아서, 사용자가 “패키지는 만들었는데 그 다음에 무엇을 해야 하지?” 상태가 되기 쉽다.

그래서 데스크톱 런처의 `Whisper runtime` 옆에 `?` 버튼을 넣었다.

이 버튼을 누르면 아래 내용을 바로 볼 수 있다.

- 번들 저장
- 노트북 저장
- Colab 열기
- GPU 런타임 선택
- 실행 셀 순서
- 결과 ZIP 가져오기
- Google Drive 사용 시 어떤 값을 바꿔야 하는지

즉, 별도 문서를 다시 찾지 않아도 현재 작업 화면 안에서 다음 단계를 확인할 수 있게 만든 것이다.

### 16.7 Google Drive 마운트 1차안

이번 세션에서 고른 현실적인 방향은 “앱이 Google Drive API에 직접 로그인하는 방식”이 아니라 “Colab 노트북 안에서 Drive를 마운트하는 방식”이다.

이 방식의 장점은 아래와 같다.

- 앱 쪽에 Google OAuth 로그인 기능을 새로 붙이지 않아도 된다.
- Colab 안에서 번들 ZIP을 Drive 경로에서 읽을 수 있다.
- 결과 자막 파일과 결과 ZIP도 Drive에 저장할 수 있다.
- 사용자가 Google Drive for Desktop을 쓰고 있으면 로컬과 Drive 사이 이동이 훨씬 단순해진다.

노트북 설정 셀에는 아래 같은 옵션이 들어간다.

- `USE_GOOGLE_DRIVE`
- `DRIVE_BUNDLE_PATH`
- `DRIVE_OUTPUT_DIR`
- `DOWNLOAD_RESULT_TO_BROWSER`

초보 관점에서 핵심은 이렇다.

- Drive를 안 쓰면 기존처럼 업로드 방식으로 그대로 사용 가능
- Drive를 쓰면 Colab이 Drive를 마운트해서 ZIP을 읽고 결과를 Drive에 저장
- 브라우저 다운로드를 계속 받고 싶으면 `DOWNLOAD_RESULT_TO_BROWSER = True`
- Drive 저장만으로 충분하면 `False`

### 16.8 Drive 연동이 “완전 자동”은 아닌 이유

중요한 제한도 있다.

- 현재 앱의 `결과 ZIP 가져오기`는 로컬 파일 선택기 기준이다.
- 그래서 PC에 Google Drive for Desktop이 없으면, Drive에 저장된 결과 ZIP을 한 번 로컬에 내려받아 가져와야 한다.

즉, 이번 1차안은 “Colab 쪽 업로드/출력 불편을 줄이는 단계”이지, “앱과 Drive가 완전히 자동 동기화되는 단계”는 아니다.

완전 자동으로 가려면 나중에 아래 같은 추가 작업이 필요하다.

- Google OAuth 2.0
- Drive API 연동
- 토큰 저장/만료 처리
- 배포용 인증 설정

그래서 이번 단계에서는 가장 복잡도가 낮고 효과가 큰 Colab 내부 Drive 마운트를 먼저 채택했다.

### 16.9 바로가기와 exe 빌드에서 배운 점

이번 세션 중 실제로 사용자가 “코드는 바뀐 것 같은데 화면에는 새 기능이 안 보인다”는 문제를 겪었다.

원인을 추적해 보니 코드 문제가 아니라 바탕화면 바로가기와 exe 빌드 산출물이 최신이 아니었던 경우가 있었다.

여기서 배운 점:

- GUI 앱은 소스 수정만으로 끝나지 않는다.
- 실제 사용자가 실행하는 `.exe`가 최신 빌드인지 확인해야 한다.
- 바탕화면 바로가기 target이 어느 exe를 가리키는지도 같이 봐야 한다.
- 실행 중인 프로세스가 있으면 기존 `dist` 폴더를 덮어쓰지 못할 수 있다.

즉, 데스크톱 앱 작업에서는 “코드 반영”과 “실행 파일 반영”을 항상 분리해서 생각해야 한다.

### 16.10 이번 세션에서 새로 추가된 핵심 파일

- `app/services/colab_transcription.py`
  - Colab 번들 생성
  - 결과 ZIP import 검증
  - Colab 노트북 payload 생성
- `docs/colab/README.md`
  - Colab handoff 흐름 문서
- `launcher.py`
  - Colab handoff UI
  - 반응형 데스크톱 레이아웃
  - `?` 도움말 버튼
  - Drive 안내 포함

### 16.11 오늘 세션 기준 확인한 테스트

- `tests/test_api.py`
- `tests/test_extraction_jobs.py`
- `tests/test_launcher.py`

이번 세션 말미 기준으로 확인한 대표 테스트 결과는 다음과 같다.

- Colab API와 런처 관련 테스트 통과
- Drive 마운트 문자열이 노트북 payload 안에 포함되는지 확인
- 반응형 런처와 Colab 도움말 문구 테스트 통과

### 16.12 초보 관점 한 줄 정리

이번 세션의 핵심은 “Whisper를 더 빠르게 돌리는 방법” 자체보다, 긴 전사 작업을 현실적으로 사용할 수 있게 만드는 실행 흐름을 정리한 것이다.

- 로컬 PC에서 할지
- Colab GPU로 넘길지
- Drive를 끼워서 번들/결과를 옮길지
- 사용자가 중간 단계에서 헷갈리지 않게 UI와 문서를 어떻게 보완할지

이 네 가지를 함께 다뤄야 실제로 쓸 수 있는 기능이 된다.
