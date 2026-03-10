const fs = require("node:fs/promises");
const { existsSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
const ffmpegPath = require("ffmpeg-static");
const { AUDIO_FORMATS } = require("./constants");
const { downloadAudio, getVideoInfo } = require("./yt-dlp");

function sanitizeBaseName(input) {
  return input
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
}

function buildOutputName(title, audioFormat) {
  const baseName = sanitizeBaseName(title || "youtube-audio") || "youtube-audio";
  return `${baseName}.${AUDIO_FORMATS[audioFormat].extension}`;
}

function buildFfmpegArgs(sourcePath, destinationPath, request) {
  const formatConfig = AUDIO_FORMATS[request.audioFormat];
  const args = ["-hide_banner", "-loglevel", "error", "-y"];

  if (request.startSeconds !== null) {
    args.push("-ss", String(request.startSeconds));
  }

  args.push("-i", sourcePath);

  if (request.endSeconds !== null) {
    const duration =
      request.startSeconds === null
        ? request.endSeconds
        : request.endSeconds - request.startSeconds;
    args.push("-t", String(duration));
  }

  args.push("-map_metadata", "-1", ...formatConfig.ffmpegArgs, destinationPath);
  return args;
}

function runFfmpeg(args) {
  return new Promise((resolve, reject) => {
    if (!ffmpegPath) {
      reject(new Error("ffmpeg 바이너리를 찾지 못했습니다."));
      return;
    }

    const pythonScript = [
      "import json, subprocess, sys",
      "command = json.loads(sys.argv[1])",
      "completed = subprocess.run(command, capture_output=True, text=True)",
      "sys.stdout.write(completed.stdout)",
      "sys.stderr.write(completed.stderr)",
      "sys.exit(completed.returncode)",
    ].join("; ");

    const child = spawn("python", ["-c", pythonScript, JSON.stringify([ffmpegPath, ...args])], {
      windowsHide: true,
      stdio: ["ignore", "ignore", "pipe"],
    });

    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }

      reject(new Error(stderr || "ffmpeg 실행 중 오류가 발생했습니다."));
    });
  });
}

async function findDownloadedSource(tempDir) {
  const items = await fs.readdir(tempDir);
  const match = items.find((item) => item.startsWith("source."));
  if (!match) {
    throw new Error("다운로드된 오디오 파일을 찾지 못했습니다.");
  }

  return path.join(tempDir, match);
}

async function cleanupTempDirectory(tempDir) {
  await fs.rm(tempDir, { recursive: true, force: true });
}

async function extractAudio(request) {
  const tempDir = path.join(os.tmpdir(), `youtube-audio-${randomUUID()}`);
  await fs.mkdir(tempDir, { recursive: true });

  try {
    const metadata = await getVideoInfo(request.url);

    await downloadAudio(request.url, path.join(tempDir, "source.%(ext)s"));

    const sourcePath = await findDownloadedSource(tempDir);
    const outputName = buildOutputName(metadata?.title, request.audioFormat);
    const outputPath = path.join(tempDir, outputName);
    const ffmpegArgs = buildFfmpegArgs(sourcePath, outputPath, request);

    await runFfmpeg(ffmpegArgs);

    if (!existsSync(outputPath)) {
      throw new Error("오디오 변환 결과 파일이 생성되지 않았습니다.");
    }

    return {
      outputName,
      outputPath,
      tempDir,
      mimeType: AUDIO_FORMATS[request.audioFormat].mimeType,
      title: metadata?.title || "youtube-audio",
    };
  } catch (error) {
    await cleanupTempDirectory(tempDir);
    throw error;
  }
}

module.exports = {
  buildFfmpegArgs,
  cleanupTempDirectory,
  extractAudio,
};
