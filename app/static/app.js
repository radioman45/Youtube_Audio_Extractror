const form = document.querySelector("#job-form");
const taskTypeInput = document.querySelector("#taskType");
const urlInput = document.querySelector("#url");
const startTimeInput = document.querySelector("#startTime");
const endTimeInput = document.querySelector("#endTime");
const audioFormatField = document.querySelector("#audio-format-field");
const audioFormatSelect = document.querySelector("#audioFormat");
const videoQualityField = document.querySelector("#video-quality-field");
const videoQualitySelect = document.querySelector("#videoQuality");
const subtitleLanguageField = document.querySelector("#subtitle-language-field");
const subtitleLanguageSelect = document.querySelector("#subtitleLanguage");
const subtitleLanguageCustomField = document.querySelector("#subtitle-language-custom-field");
const subtitleLanguageCustomInput = document.querySelector("#subtitleLanguageCustom");
const batchModeField = document.querySelector("#batch-mode-field");
const batchModeSelect = document.querySelector("#batchMode");
const rangeHelp = document.querySelector("#range-help");
const folderButton = document.querySelector("#folder-button");
const folderDisplay = document.querySelector("#folder-display");
const folderHelp = document.querySelector("#folder-help");
const themeToggle = document.querySelector("#theme-toggle");
const submitButton = document.querySelector("#submit-button");
const statusText = document.querySelector("#status-text");
const progressShell = document.querySelector("#progress-shell");
const progressTitle = document.querySelector("#progress-title");
const progressFill = document.querySelector("#progress-fill");
const progressLabel = document.querySelector("#progress-label");
const progressMessage = document.querySelector("#progress-message");
const progressTrack = document.querySelector(".progress-track");
const batchSummary = document.querySelector("#batch-summary");
const batchTotal = document.querySelector("#batch-total");
const batchCompleted = document.querySelector("#batch-completed");
const batchFailed = document.querySelector("#batch-failed");
const modeLabel = document.querySelector("#mode-label");
const modeTitle = document.querySelector("#mode-title");
const modeDescription = document.querySelector("#mode-description");
const modeButtons = Array.from(document.querySelectorAll(".mode-button"));

const MODE_CONFIG = {
  audio: {
    label: "오디오 추출",
    title: "원하는 형식으로 오디오를 추출합니다.",
    description: "전체 또는 특정 구간을 MP3, WAV, AAC 등으로 저장합니다.",
    submitLabel: "오디오 추출 시작",
    doneLabel: "오디오 추출이 완료되었습니다.",
  },
  song_mp3: {
    label: "노래 MP3 추출",
    title: "고음질 MP3에 메타데이터를 함께 저장합니다.",
    description: "제목, 아티스트, 앨범아트까지 포함한 MP3를 만듭니다.",
    submitLabel: "노래 MP3 추출 시작",
    doneLabel: "노래 MP3 추출이 완료되었습니다.",
  },
  video: {
    label: "영상 추출",
    title: "선택한 화질의 영상을 저장합니다.",
    description: "360p부터 8K까지 선택하고 필요한 구간만 잘라낼 수 있습니다.",
    submitLabel: "영상 추출 시작",
    doneLabel: "영상 추출이 완료되었습니다.",
  },
  subtitle: {
    label: "자막 추출",
    title: "선택한 언어의 자막을 SRT로 저장합니다.",
    description: "원하는 언어와 구간만 골라 .srt 파일로 받습니다.",
    submitLabel: "자막 추출 시작",
    doneLabel: "자막 추출이 완료되었습니다.",
  },
  batch: {
    label: "재생목록/채널 다운로드",
    title: "재생목록 또는 채널 전체에 일괄 적용합니다.",
    description: "선택한 기능을 전체 항목에 적용하고 결과를 ZIP으로 묶어 저장합니다.",
    submitLabel: "배치 다운로드 시작",
    doneLabel: "배치 다운로드가 완료되었습니다.",
  },
};

const BATCH_MODE_LABELS = {
  audio: "오디오 추출",
  song_mp3: "노래 MP3 추출",
  video: "영상 추출",
  subtitle: "자막 추출",
};

const folderState = {
  handle: null,
};

let currentMode = "audio";
const THEME_STORAGE_KEY = "ytme-theme";

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function getThemeLabel(theme) {
  return theme === "dark" ? "라이트 모드" : "다크 모드";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeToggle.textContent = getThemeLabel(theme);
  themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
}

function initializeTheme() {
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = savedTheme || (prefersDark ? "dark" : "light");
  applyTheme(theme);
}

function toggleTheme() {
  const currentTheme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const nextTheme = currentTheme === "dark" ? "light" : "dark";
  window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  applyTheme(nextTheme);
}

function setStatus(message, state = "idle") {
  statusText.textContent = message;
  statusText.dataset.state = state;
}

function setBusy(isBusy) {
  for (const element of form.querySelectorAll("input, select, button")) {
    if (element === folderButton) {
      continue;
    }
    element.disabled = isBusy;
  }

  submitButton.disabled = isBusy;
  folderButton.disabled = isBusy || typeof window.showDirectoryPicker !== "function";
  for (const button of modeButtons) {
    button.disabled = isBusy;
  }
}

function setBatchSummary(details = {}) {
  const total = Number(details.total || 0);
  const completed = Number(details.completed || 0);
  const failed = Number(details.failed || 0);

  if (total > 0) {
    batchSummary.classList.remove("hidden");
    batchTotal.textContent = String(total);
    batchCompleted.textContent = String(completed);
    batchFailed.textContent = String(failed);
    return;
  }

  batchSummary.classList.add("hidden");
  batchTotal.textContent = "0";
  batchCompleted.textContent = "0";
  batchFailed.textContent = "0";
}

function setProgress(progress, message = "", state = "idle", details = {}) {
  const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));

  progressShell.classList.remove("hidden");
  progressShell.dataset.state = state;
  progressShell.setAttribute("aria-hidden", "false");
  progressFill.style.width = `${safeProgress}%`;
  progressLabel.textContent = `${Math.round(safeProgress)}%`;
  progressTrack.setAttribute("aria-valuenow", String(Math.round(safeProgress)));
  progressMessage.textContent = message || "작업을 진행하는 중입니다.";
  progressTitle.textContent = currentMode === "batch" ? "배치 작업 진행률" : `${MODE_CONFIG[currentMode].label} 진행률`;
  setBatchSummary(details);
}

function resetProgress() {
  progressShell.classList.add("hidden");
  progressShell.dataset.state = "idle";
  progressShell.setAttribute("aria-hidden", "true");
  progressFill.style.width = "0%";
  progressLabel.textContent = "0%";
  progressTrack.setAttribute("aria-valuenow", "0");
  progressMessage.textContent = "작업을 준비하는 중입니다.";
  setBatchSummary({});
}

function getEffectiveSubtitleLanguage() {
  if (subtitleLanguageSelect.value === "custom") {
    return String(subtitleLanguageCustomInput.value || "").trim();
  }
  return subtitleLanguageSelect.value;
}

function syncSubtitleLanguageUi() {
  const shouldShowCustom =
    !subtitleLanguageField.classList.contains("hidden") && subtitleLanguageSelect.value === "custom";
  subtitleLanguageCustomField.classList.toggle("hidden", !shouldShowCustom);
}

function syncModeUi() {
  taskTypeInput.value = currentMode;
  for (const button of modeButtons) {
    button.classList.toggle("active", button.dataset.mode === currentMode);
  }

  const effectiveBatchMode = batchModeSelect.value;
  const effectiveMode = currentMode === "batch" ? effectiveBatchMode : currentMode;

  modeLabel.textContent = MODE_CONFIG[currentMode].label;
  modeTitle.textContent = MODE_CONFIG[currentMode].title;
  modeDescription.textContent =
    currentMode === "batch"
      ? `${MODE_CONFIG.batch.description} 현재 적용 기능: ${BATCH_MODE_LABELS[effectiveBatchMode]}.`
      : MODE_CONFIG[currentMode].description;

  batchModeField.classList.toggle("hidden", currentMode !== "batch");
  audioFormatField.classList.toggle("hidden", !(currentMode === "audio" || (currentMode === "batch" && effectiveMode === "audio")));
  videoQualityField.classList.toggle("hidden", !(currentMode === "video" || (currentMode === "batch" && effectiveMode === "video")));
  subtitleLanguageField.classList.toggle(
    "hidden",
    !(currentMode === "subtitle" || (currentMode === "batch" && effectiveMode === "subtitle"))
  );

  rangeHelp.textContent =
    currentMode === "batch"
      ? "시간을 비워 두면 전체 구간을 처리합니다. 배치 다운로드에서는 같은 시간 범위를 모든 항목에 적용합니다."
      : "시간을 비워 두면 전체 구간을 처리합니다.";

  submitButton.textContent =
    currentMode === "batch"
      ? `${BATCH_MODE_LABELS[effectiveBatchMode]} 배치 다운로드 시작`
      : MODE_CONFIG[currentMode].submitLabel;

  syncSubtitleLanguageUi();
}

function extractFilename(disposition, fallbackName) {
  if (!disposition) {
    return fallbackName;
  }

  const utfMatch = disposition.match(/filename\*=utf-8''([^;]+)/i);
  if (utfMatch) {
    return decodeURIComponent(utfMatch[1]);
  }

  const asciiMatch = disposition.match(/filename="?([^"]+)"?/i);
  if (asciiMatch) {
    return asciiMatch[1];
  }

  return fallbackName;
}

function triggerBrowserDownload(blob, filename) {
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}

async function writeBlobToFolder(blob, filename) {
  if (!folderState.handle) {
    triggerBrowserDownload(blob, filename);
    return "브라우저 다운로드를 시작했습니다.";
  }

  try {
    if (typeof folderState.handle.queryPermission === "function") {
      let permission = await folderState.handle.queryPermission({ mode: "readwrite" });
      if (permission !== "granted" && typeof folderState.handle.requestPermission === "function") {
        permission = await folderState.handle.requestPermission({ mode: "readwrite" });
      }

      if (permission !== "granted") {
        throw new Error("선택한 폴더에 쓸 권한이 필요합니다.");
      }
    }

    const fileHandle = await folderState.handle.getFileHandle(filename, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(blob);
    await writable.close();
    return `${folderState.handle.name} 폴더에 저장했습니다.`;
  } catch (error) {
    console.error(error);
    triggerBrowserDownload(blob, filename);
    return "폴더 저장에 실패해 브라우저 다운로드로 전환했습니다.";
  }
}

async function handleFolderPick() {
  if (typeof window.showDirectoryPicker !== "function") {
    setStatus("이 브라우저에서는 폴더 직접 저장을 지원하지 않습니다.", "error");
    return;
  }

  try {
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    folderState.handle = handle;
    folderDisplay.textContent = handle.name;
    setStatus(`${handle.name} 폴더를 저장 위치로 선택했습니다.`, "success");
  } catch (error) {
    if (error && error.name !== "AbortError") {
      console.error(error);
      setStatus("폴더 선택 중 오류가 발생했습니다.", "error");
    }
  }
}

function buildPayload() {
  const commonPayload = {
    taskType: currentMode,
    url: String(urlInput.value || "").trim(),
    startTime: String(startTimeInput.value || "").trim() || null,
    endTime: String(endTimeInput.value || "").trim() || null,
  };

  if (currentMode === "audio") {
    return {
      fallbackName: `youtube-audio.${audioFormatSelect.value}`,
      payload: {
        ...commonPayload,
        audioFormat: audioFormatSelect.value,
      },
    };
  }

  if (currentMode === "song_mp3") {
    return {
      fallbackName: "youtube-song.mp3",
      payload: commonPayload,
    };
  }

  if (currentMode === "video") {
    return {
      fallbackName: "youtube-video.mp4",
      payload: {
        ...commonPayload,
        videoQuality: videoQualitySelect.value,
      },
    };
  }

  if (currentMode === "subtitle") {
    return {
      fallbackName: "youtube-subtitles.srt",
      payload: {
        ...commonPayload,
        subtitleLanguage: getEffectiveSubtitleLanguage(),
      },
    };
  }

  const batchMode = batchModeSelect.value;
  const payload = {
    ...commonPayload,
    taskType: "batch",
    batchMode,
    audioFormat: audioFormatSelect.value,
    videoQuality: videoQualitySelect.value,
    subtitleLanguage: getEffectiveSubtitleLanguage() || "ko",
  };

  return {
    fallbackName: `youtube-batch-${batchMode}.zip`,
    payload,
  };
}

async function readErrorMessage(response, fallbackMessage) {
  try {
    const errorBody = await response.json();
    return errorBody.detail || errorBody.error || fallbackMessage;
  } catch (error) {
    console.error(error);
    return fallbackMessage;
  }
}

async function fetchDownload(downloadUrl, fallbackName) {
  const response = await fetch(downloadUrl);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "생성된 파일을 다운로드하지 못했습니다."));
  }

  const blob = await response.blob();
  const filename = extractFilename(response.headers.get("Content-Disposition"), fallbackName);
  const saveMessage = await writeBlobToFolder(blob, filename);
  return { filename, saveMessage };
}

async function waitForJob(jobId, fallbackName) {
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, "작업 상태를 조회하지 못했습니다."));
    }

    const job = await response.json();
    setProgress(job.progress || 0, job.message || "처리 중입니다.", job.status || "processing", job.details || {});

    if (job.status === "failed") {
      throw new Error(job.error || job.message || "작업이 실패했습니다.");
    }

    if (job.status === "completed") {
      return {
        filename: job.filename || fallbackName,
        downloadUrl: job.downloadUrl,
        message: job.message,
        details: job.details || {},
      };
    }

    await sleep(1000);
  }
}

async function handleSubmit(event) {
  event.preventDefault();

  const config = buildPayload();
  setBusy(true);
  setProgress(0, "작업을 준비하는 중입니다.", "busy", currentMode === "batch" ? { total: 0, completed: 0, failed: 0 } : {});
  setStatus(`${MODE_CONFIG[currentMode].label} 작업을 시작합니다.`, "busy");

  try {
    const createResponse = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(config.payload),
    });

    if (!createResponse.ok) {
      throw new Error(await readErrorMessage(createResponse, "작업을 시작하지 못했습니다."));
    }

    const createdJob = await createResponse.json();
    setProgress(
      createdJob.progress || 0,
      createdJob.message || "작업을 준비하는 중입니다.",
      createdJob.status || "queued",
      createdJob.details || {}
    );

    const completedJob = await waitForJob(createdJob.jobId, config.fallbackName);
    const result = await fetchDownload(completedJob.downloadUrl, completedJob.filename);
    setProgress(100, completedJob.message || MODE_CONFIG[currentMode].doneLabel, "success", completedJob.details || {});
    setStatus(`${MODE_CONFIG[currentMode].doneLabel} ${result.saveMessage}`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "작업이 실패했습니다.";
    setProgress(Number(progressLabel.textContent.replace("%", "")) || 0, message, "error");
    setStatus(message, "error");
  } finally {
    setBusy(false);
  }
}

if (typeof window.showDirectoryPicker !== "function") {
  folderButton.disabled = true;
  folderHelp.textContent =
    "Chrome 또는 Edge에서는 폴더 직접 저장을 지원합니다. 그 외 브라우저에서는 기본 다운로드 폴더를 사용합니다.";
}

for (const button of modeButtons) {
  button.addEventListener("click", () => {
    currentMode = button.dataset.mode || "audio";
    syncModeUi();
    resetProgress();
    setStatus("준비되었습니다.", "idle");
  });
}

subtitleLanguageSelect.addEventListener("change", syncSubtitleLanguageUi);
batchModeSelect.addEventListener("change", syncModeUi);
folderButton.addEventListener("click", handleFolderPick);
themeToggle.addEventListener("click", toggleTheme);
form.addEventListener("submit", handleSubmit);

initializeTheme();
syncModeUi();
