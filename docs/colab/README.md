# Colab Handoff Workflow

This project supports a manual Colab GPU handoff flow for uploaded audio subtitle jobs.

## Intended flow

1. Choose `subtitle` mode.
2. Choose `Whisper` as the subtitle engine.
3. Choose `audio file` as the source.
4. Choose `Google Colab GPU` as the runtime.
5. Upload the audio file.
6. Download the generated Colab bundle ZIP.
7. Download the notebook template from the app.
8. Open Google Colab and run the notebook manually.
9. Choose either:
   - upload the bundle ZIP directly in Colab, or
   - mount Google Drive in the notebook and point it at the bundle ZIP path.
10. Download the generated `colab-result.zip` or save it into Google Drive.
11. Import the result ZIP back into the app.

## Notes

- This is a manual handoff flow. The app does not log into Google Colab for the user.
- The notebook now supports optional Google Drive mounting for bundle input and result output.
- Free Colab GPU availability is not guaranteed.
- Runtime disconnects can happen. If the notebook fails, rerun it and import the new result ZIP.
- The local `faster-whisper` path remains available as the default fallback.

## Result package contract

The Colab notebook must produce a ZIP file that contains:

- the generated subtitle output file
- `result.json`

The `result.json` file must include:

- `jobId`
- `sourceSha256`
- `subtitleFormat`
- `downloadName`
- `resultFile`

Optional fields may include:

- `whisperModel`
- `device`
- `language`
- `segmentCount`
- `durationSeconds`
- `generator`
