# 디버깅 기록

## 2026-03-11 오디오 추출 에러

### 증상

- UI에서 오디오 추출 진행률이 약 `15%`에서 멈춤
- 상태 문구: `작업 중 예기치 않은 오류가 발생했습니다.`
- 사용자 제공 재현 링크:
  - `https://www.youtube.com/watch?v=-csBkVJNTdA`

### 재현 방법

아래 코드로 실제 추출을 직접 실행해 재현했다.

```powershell
.venv\Scripts\python.exe -c "from app.services.extractor import extract_audio, ExtractionOptions; extract_audio(ExtractionOptions(url='https://www.youtube.com/watch?v=-csBkVJNTdA', audio_format='mp3'))"
```

### 관찰 내용

- 영상 메타데이터 조회는 정상
- `yt-dlp` 다운로드도 정상
- 오디오 파일도 실제로 생성됨
- 하지만 ffmpeg 실행 후 `subprocess` 내부 reader thread에서 아래 예외가 발생함

```text
UnicodeDecodeError: 'cp949' codec can't decode byte 0x9f ...
```

### 원인

원인은 [app/services/extractor.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/app/services/extractor.py)의 ffmpeg 실행 코드였다.

기존 구현:

```python
subprocess.run(command, capture_output=True, text=True, check=False)
```

문제점:

- Windows 기본 인코딩(`cp949`)으로 ffmpeg stderr/stdout을 텍스트 디코딩함
- 특정 영상에서 ffmpeg 출력 바이트가 `cp949`로 해석되지 않아 `UnicodeDecodeError` 발생
- 이 예외가 실행 환경에 따라 작업 실패처럼 보일 수 있음

### 수정 내용

`run_ffmpeg()`를 다음 방식으로 변경했다.

1. `text=True` 제거
2. 바이트로 출력 수집
3. `utf-8`, `cp949`, 최종 `errors='replace'` 순서로 안전 디코딩

핵심 수정:

```python
completed = subprocess.run(command, capture_output=True, text=False, check=False)
stderr_text = decode_subprocess_output(completed.stderr)
```

### 검증 결과

- 같은 링크로 다시 추출 시 정상 완료
- 동일 링크로 `run_audio_job()` 경로도 점검
- 자동 테스트 통과:

```powershell
.venv\Scripts\python.exe -m pytest
```

결과:

- `26 passed`

### 재발 방지 규칙

앞으로 ffmpeg / yt-dlp / 외부 프로세스 호출 시 아래 규칙을 지킨다.

1. `subprocess.run(..., text=True)`를 외부 멀티바이트 출력 처리에 사용하지 않는다.
2. stderr/stdout은 우선 `bytes`로 받고, 애플리케이션이 직접 디코딩한다.
3. 디코딩은 `utf-8` 우선, 필요 시 로컬 인코딩 fallback, 마지막에는 `errors='replace'`를 사용한다.
4. Windows에서 한글/특수문자 포함 출력이 가능한 링크로 회귀 테스트를 수행한다.
5. UI에 `예기치 않은 오류`가 뜨면 먼저 background job 내부의 외부 프로세스 stderr 디코딩 경로를 의심한다.

### 관련 파일

- [app/services/extractor.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/app/services/extractor.py)
- [app/main.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/app/main.py)

## 추가 메모: EXE 재빌드 잠금 이슈

### 현상

- `dist\YouTubeAudioExtractor.exe` 재빌드 중 아래 오류가 여러 번 발생

```text
PermissionError: [WinError 5] 액세스가 거부되었습니다: '...\\dist\\YouTubeAudioExtractor.exe'
```

### 원인

- 기존 `YouTubeAudioExtractor.exe` 프로세스가 실행 중이라 파일이 잠겨 있었음

### 대응

- 빌드 전 `YouTubeAudioExtractor` 프로세스 종료 후 재빌드

### 재발 방지 규칙

1. EXE 재빌드 전 `Get-Process YouTubeAudioExtractor`로 실행 여부 확인
2. 실행 중이면 먼저 종료 후 빌드
3. 재빌드 자동화가 필요하면 빌드 스크립트 앞단에 잠금 확인 로직 추가 검토

## 2026-03-11 영상 추출 오류

### 증상

- UI에서 `영상 추출` 작업이 진행되다가 실패
- 진행률은 다운로드 이후 후처리 구간에서 멈춤
- 사용자 제공 재현 화면 기준 설정:
  - URL: `https://www.youtube.com/watch?v=jvBBcKfQ03c`
  - 화질: `1080p`
  - 구간: `0 ~ 30`

### 재현 방법

```powershell
.venv\Scripts\python.exe -c "from app.services.video_extractor import extract_video, VideoExtractionOptions; extract_video(VideoExtractionOptions(url='https://www.youtube.com/watch?v=jvBBcKfQ03c', video_quality='1080p', start_time='0', end_time='30'))"
```

### 실제 예외

```text
ExtractionRuntimeError: Error opening output files: Invalid argument
```

### 원인

원인은 [app/services/video_extractor.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/app/services/video_extractor.py)의 `build_video_download_name()`였다.

구간 추출일 때는 파일명을 다음처럼 직접 만들고 있었다.

```python
f"{title}_{video_quality}_{seconds_to_label(start_seconds)}_to_{seconds_to_label(end_seconds)}.mp4"
```

문제점:

- 이 경로에서는 `title`에 대해 `sanitize_filename()`를 적용하지 않았음
- 재현 링크 제목에는 `?`가 포함되어 있었음
- Windows 파일명 금지 문자가 그대로 출력 경로에 들어가면서 ffmpeg가 `Invalid argument`로 실패

### 수정 내용

- `build_video_download_name()`에서 먼저 `safe_title = sanitize_filename(title)` 적용
- 전체 영상 저장과 구간 저장 모두 정규화된 제목을 사용하도록 변경

핵심 수정:

```python
safe_title = sanitize_filename(title)
```

### 검증 결과

- 같은 링크와 같은 구간으로 다시 실행 시 정상 완료
- 생성 파일명 예시:

```text
학생들이 이걸 참을 수 있을까.. 99만원짜리 애플 맥북 네오 첫인상!_1080p_00-00_to_00-30.mp4
```

- 테스트 추가:
  - 제목에 `:?*` 등 금지 문자가 있어도 안전한 영상 파일명이 생성되는지 확인

```powershell
.venv\Scripts\python.exe -m pytest
```

결과:

- `27 passed`

### 재발 방지 규칙

1. 다운로드 결과 파일명은 작업 유형과 무관하게 항상 `sanitize_filename()`를 거친다.
2. 범위 추출용 별도 파일명 빌더를 만들 때 raw title 문자열을 직접 이어 붙이지 않는다.
3. Windows 금지 문자(`<>:\"/\\|?*`)가 포함된 제목을 테스트 케이스에 유지한다.

## 2026-03-12 `This page is protected` 보호 페이지 오인

### 증상

- 앱 실행 후 자막/모델 문제로 오해하기 쉬운 `This page is protected` 화면이 반복적으로 표시됨
- 사용자는 Whisper 모델 다운로드 실패와 같은 문제로 인식했지만, 실제 앱 내부 에러 문구가 아니라 브라우저/보안 페이지였음

### 원인

- 최신 데스크톱 런처가 아니라 예전 웹 기반 산출물을 실행하고 있었음
- 구형 실행 파일은 `localhost` 페이지를 띄우는 구조였고, 회사 보안 환경에서 이 로컬 페이지가 보호 페이지로 대체 표시됨

### 대응

- 최신 실행 경로를 `dist/YouTubeAudioExtractorDesktop/YouTubeAudioExtractorDesktop.exe`로 통일
- 바탕화면 바로가기 `YouTube Audio Extractor Desktop.lnk`, `YouTube Audio Extractor.lnk`를 모두 최신 데스크톱 빌드로 재지정
- 구형 웹 산출물은 `dist/YouTubeAudioExtractor.web-legacy.disabled`로 비활성화해 혼동 가능성을 줄임

### 검증

- 최신 데스크톱 빌드는 실행 후 `8000`, `18000` 포트를 열지 않음
- 새 실행 파일은 8초 이상 정상 유지되는 것을 확인

### 재발 방지 규칙

1. 실행 장애를 볼 때는 먼저 “어떤 `.exe`를 눌렀는지”부터 확인한다.
2. `dist` 안에 신구 산출물이 함께 있으면 최신 실행 파일 경로를 문서와 바로가리에서 명시한다.
3. 브라우저 화면이 뜬다면 앱 내부 에러와 보안/브라우저 개입 문제를 구분한다.

## 2026-03-12 Whisper `base` 모델 다운로드 실패

### 증상

- 앱에서 아래 메시지로 Whisper 전사가 시작되지 않음

```text
Whisper model 'base' could not be downloaded. Check internet access, disk space, or choose a smaller model like 'base'.
```

### 재현 및 관찰

- `huggingface_hub.snapshot_download()`는 `LocalEntryNotFoundError`로 실패
- 직접 `model.bin`을 요청하면 `SSL: CERTIFICATE_VERIFY_FAILED` 또는 `Website Blocking` 응답이 관찰됨
- 회사망에서 `huggingface.co`는 차단되지만 `hf-mirror.com` 경로는 접근 가능했음
- 추가로 `faster-whisper-base` 저장소에는 `preprocessor_config.json`이 없는데, 로컬 완전성 검사에서 이 파일을 필수로 보고 있어 fallback 성공 후에도 실패할 수 있었음

### 원인

1. 공식 Hugging Face 호스트가 회사/보안 네트워크에서 차단됨
2. 앱의 수동 다운로드 경로가 Windows 신뢰 저장소를 활용하지 않아 TLS 검증에 취약했음
3. 수동 fallback의 필수 파일 가정이 실제 저장소 구조와 맞지 않았음

### 수정 내용

- [app/services/whisper_subtitle_extractor.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/app/services/whisper_subtitle_extractor.py)
  - Windows 신뢰 저장소를 활용하는 `truststore` 기반 HTTP 클라이언트 추가
  - 공식 허브 실패 시 대체 미러(`hf-mirror.com`) 자동 재시도 추가
  - 모델 저장소 파일 검사에서 `preprocessor_config.json`을 선택 파일로 완화
  - 실패 시 실제 원인에 가까운 문장을 보여주도록 예외 메시지 개선
- [requirements.txt](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/requirements.txt)
  - `truststore` 추가
- [tests/test_whisper_subtitle_extractor.py](/C:/Users/sv61529/Desktop/myprojects/02_Youtube_Audio_extractror/tests/test_whisper_subtitle_extractor.py)
  - 엔드포인트 fallback 및 로컬 모델 완전성 테스트 추가

### 검증 결과

- `pytest` 전체 통과: `57 passed`
- `base` 모델을 실제로 아래 경로에 캐시 완료:
  - `C:\\Users\\sv61529\\AppData\\Local\\YouTubeAudioExtractor\\whisper-models\\base`
- `load_whisper_model('base')`가 로컬 캐시에서 정상 로드되는 것 확인
- 최신 데스크톱 `.exe` 재빌드 후 실행 유지 확인

### 재발 방지 규칙

1. 모델 다운로드 실패는 단순 네트워크 에러로 뭉뚱그리지 말고, 인증서 실패/호스트 차단/저장소 파일 구조를 분리해서 본다.
2. 외부 허브 의존 기능은 공식 경로 하나에만 기대지 말고 fallback 경로를 설계한다.
3. 로컬 캐시 완전성 검사는 실제 모델 저장소 구조와 맞춰 유지한다.
4. 사용자 PC에서 실제로 모델 캐시가 생성되는지까지 확인해야 “해결”로 본다.
