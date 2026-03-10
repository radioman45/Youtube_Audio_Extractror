const { spawn } = require("node:child_process");

let ensurePromise = null;

function runPython(args) {
  return new Promise((resolve, reject) => {
    const child = spawn("python", args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }

      reject(new Error(stderr || `python ${args.join(" ")} failed with code ${code}`));
    });
  });
}

async function checkYtDlpReady() {
  try {
    await runPython(["-m", "yt_dlp", "--version"]);
    return true;
  } catch {
    return false;
  }
}

async function ensureYtDlpBinary() {
  if (ensurePromise) {
    return ensurePromise;
  }

  ensurePromise = (async () => {
    if (await checkYtDlpReady()) {
      return "python -m yt_dlp";
    }

    await runPython(["-m", "pip", "install", "--user", "yt-dlp"]);

    if (!(await checkYtDlpReady())) {
      throw new Error("yt-dlp 설치에 실패했습니다.");
    }

    return "python -m yt_dlp";
  })();

  try {
    return await ensurePromise;
  } finally {
    ensurePromise = null;
  }
}

async function getVideoInfo(url) {
  await ensureYtDlpBinary();
  const { stdout } = await runPython([
    "-m",
    "yt_dlp",
    "--js-runtimes",
    "node",
    "--skip-download",
    "--dump-single-json",
    "--no-playlist",
    url,
  ]);

  return JSON.parse(stdout);
}

async function downloadAudio(url, outputTemplate) {
  await ensureYtDlpBinary();
  await runPython([
    "-m",
    "yt_dlp",
    "--js-runtimes",
    "node",
    "--no-playlist",
    "-f",
    "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
    "-o",
    outputTemplate,
    url,
  ]);
}

module.exports = {
  checkYtDlpReady,
  downloadAudio,
  ensureYtDlpBinary,
  getVideoInfo,
};
