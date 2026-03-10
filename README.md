# YouTube Audio Extractor

Local FastAPI app for extracting audio from a YouTube URL.

## Features

- Full audio export when only a YouTube URL is provided
- Range-based clipping when start and end times are provided
- Output format selection: `mp3`, `m4a`, `wav`, `opus`
- Optional save-folder picker in Chromium browsers
- Browser download fallback when direct folder save is not supported

## Setup

1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Start the app

```powershell
uvicorn app.main:app --reload
```

Quick start on Windows:

```powershell
.\start_app.ps1
```

or double-click `start_app.bat`.

4. Open the app

```text
http://127.0.0.1:8000
```

## Time Format

- `90`
- `01:30`
- `00:01:30`

If both time fields are blank, the app exports the full duration.

## Save Folder Behavior

- In Chrome or Edge on `localhost`, you can choose a save folder and write the extracted file directly there.
- In browsers without the File System Access API, the app falls back to the browser's default download folder.
- Folder selection is session-based and may need to be picked again after a refresh.

## Tests

```powershell
pytest
```

## Notes

- This app extracts the audio track from a YouTube video.
- It does not include ML-based vocal removal or stem separation.
- `imageio-ffmpeg` provides the ffmpeg binary used by the app, so a separate global ffmpeg install is not required.
- `yt-dlp` behavior can change depending on YouTube availability and restrictions.
