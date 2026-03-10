# YouTube Multi Extractor

로컬 FastAPI 앱으로 YouTube 오디오, 노래 MP3, 영상, 자막, 재생목록/채널 배치 다운로드를 처리합니다.

## 주요 기능

- 오디오 추출: 전체 또는 특정 구간, `mp3` `wav` `aac` `m4a` `opus`
- 노래 MP3 추출: 최고 음질 MP3, 메타데이터, 앨범아트 임베드
- 영상 추출: 전체 또는 구간 저장, `360p`부터 `8K`까지 화질 선택
- 자막 추출: 언어 선택, 구간 필터링, `.srt` 출력
- 재생목록/채널 다운로드: 오디오/노래 MP3/영상/자막 기능을 전체 항목에 일괄 적용

## 실행 방법

1. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. 의존성 설치

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. 앱 실행

```powershell
uvicorn app.main:app --reload
```

Windows 빠른 실행:

```powershell
.\start_app.ps1
```

또는 `start_app.bat`를 실행합니다.

4. 브라우저 열기

```text
http://127.0.0.1:8000
```

## 시간 형식

- `90`
- `01:30`
- `00:01:30`

시작/종료 시간을 비우면 전체 구간을 처리합니다.

## 저장 폴더 동작

- Chrome 또는 Edge에서는 선택한 폴더에 바로 저장할 수 있습니다.
- 폴더 직접 저장을 지원하지 않는 브라우저에서는 기본 다운로드 폴더를 사용합니다.

## 테스트

```powershell
pytest
```

## 참고

- 실제 다운로드 동작은 `yt-dlp`와 YouTube 측 상태에 영향을 받습니다.
- `imageio-ffmpeg`가 ffmpeg 실행 파일을 제공합니다.
- 고화질 또는 자동 생성 자막은 원본 가용성에 따라 결과가 달라질 수 있습니다.
