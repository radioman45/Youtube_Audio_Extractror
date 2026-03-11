from pathlib import Path

import extractor

from app.services.extractor import ExtractionResult


def test_cli_writes_srt_to_current_directory(monkeypatch, tmp_path: Path, capsys):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    srt_path = temp_dir / "sample_whisper_base_ko.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "extractor.extract_whisper_subtitles",
        lambda options: ExtractionResult(
            file_path=srt_path,
            download_name="sample_whisper_base_ko.srt",
            temp_dir=temp_dir,
            media_type="application/x-subrip; charset=utf-8",
        ),
    )

    exit_code = extractor.main(
        [
            "--url",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--model",
            "base",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Success:" in captured.out
    assert (tmp_path / "sample_whisper_base_ko.srt").exists()
