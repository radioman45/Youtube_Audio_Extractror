const express = require("express");
const path = require("node:path");
const { ZodError } = require("zod");
const { extractAudio, cleanupTempDirectory } = require("./extractor");
const { InputError, parseExtractionRequest } = require("./validation");
const { checkYtDlpReady } = require("./yt-dlp");

function createApp() {
  const app = express();

  app.use(express.json());
  app.use(express.static(path.join(process.cwd(), "public")));

  app.get("/api/health", async (_req, res) => {
    const ytDlpReady = await checkYtDlpReady();

    res.json({
      ok: true,
      ytDlpReady,
      ffmpegBundled: true,
      formats: ["mp3", "m4a", "wav", "opus"],
    });
  });

  app.post("/api/extract", async (req, res, next) => {
    let result = null;

    try {
      const request = parseExtractionRequest(req.body);
      result = await extractAudio(request);

      res.type(result.mimeType);
      res.download(result.outputPath, result.outputName, async (error) => {
        await cleanupTempDirectory(result.tempDir);
        if (error && !res.headersSent) {
          next(error);
        }
      });
    } catch (error) {
      if (result?.tempDir) {
        await cleanupTempDirectory(result.tempDir);
      }
      next(error);
    }
  });

  app.use((error, _req, res, _next) => {
    const statusCode = error instanceof ZodError || error instanceof InputError ? 400 : 500;
    const message =
      error instanceof ZodError
        ? error.issues[0]?.message || "입력값을 확인해 주세요."
        : error instanceof InputError
          ? error.message
        : error.message || "오디오 추출 중 오류가 발생했습니다.";

    res.status(statusCode).json({
      ok: false,
      message,
    });
  });

  return app;
}

module.exports = {
  createApp,
};
