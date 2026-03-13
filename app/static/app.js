const form = document.querySelector("#job-form");
const taskTypeInput = document.querySelector("#taskType");
const linkSection = document.querySelector("#link-section");
const urlInput = document.querySelector("#url");
const startTimeInput = document.querySelector("#startTime");
const endTimeInput = document.querySelector("#endTime");
const audioFormatField = document.querySelector("#audio-format-field");
const audioFormatSelect = document.querySelector("#audioFormat");
const videoQualityField = document.querySelector("#video-quality-field");
const videoQualitySelect = document.querySelector("#videoQuality");
const subtitleEngineField = document.querySelector("#subtitle-engine-field");
const subtitleEngineSelect = document.querySelector("#subtitleEngine");
const subtitleSourceField = document.querySelector("#subtitle-source-field");
const subtitleSourceSelect = document.querySelector("#subtitleSource");
const subtitleLanguageField = document.querySelector("#subtitle-language-field");
const subtitleLanguageSelect = document.querySelector("#subtitleLanguage");
const subtitleFormatField = document.querySelector("#subtitle-format-field");
const subtitleFormatSelect = document.querySelector("#subtitleFormat");
const subtitleLanguageCustomField = document.querySelector("#subtitle-language-custom-field");
const subtitleLanguageCustomInput = document.querySelector("#subtitleLanguageCustom");
const whisperModelField = document.querySelector("#whisper-model-field");
const whisperModelSelect = document.querySelector("#whisperModel");
const whisperDeviceField = document.querySelector("#whisper-device-field");
const whisperDeviceSelect = document.querySelector("#whisperDevice");
const whisperRuntimeField = document.querySelector("#whisper-runtime-field");
const whisperRuntimeSelect = document.querySelector("#whisperRuntime");
const audioUploadField = document.querySelector("#audio-upload-field");
const audioFileInput = document.querySelector("#audioFile");
const audioUploadHelp = document.querySelector("#audio-upload-help");
const vadFilterField = document.querySelector("#vad-filter-field");
const vadFilterCheckbox = document.querySelector("#vadFilter");
const subtitleEngineHelp = document.querySelector("#subtitle-engine-help");
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
const colabPanel = document.querySelector("#colab-panel");
const colabStatusBadge = document.querySelector("#colab-status-badge");
const colabPanelCopy = document.querySelector("#colab-panel-copy");
const colabJobId = document.querySelector("#colab-job-id");
const colabBundleName = document.querySelector("#colab-bundle-name");
const colabResultName = document.querySelector("#colab-result-name");
const colabDownloadBundleButton = document.querySelector("#colab-download-bundle");
const colabDownloadNotebookButton = document.querySelector("#colab-download-notebook");
const colabOpenHomeButton = document.querySelector("#colab-open-home");
const colabImportResultButton = document.querySelector("#colab-import-result");
const colabPanelHelp = document.querySelector("#colab-panel-help");
const colabResultFileInput = document.querySelector("#colab-result-file");

const MODE_CONFIG = {
  audio: {
    label: "오디오 추출",
    title: "전체 또는 특정 구간의 오디오를 원하는 형식으로 추출합니다.",
    description: "MP3, WAV, AAC 등으로 변환할 수 있고, 시작/종료 시간을 입력하면 필요한 구간만 처리합니다.",
    submitLabel: "오디오 추출 시작",
    doneLabel: "오디오 추출이 완료되었습니다.",
  },
  song_mp3: {
    label: "노래 MP3 추출",
    title: "고음질 MP3와 메타데이터를 함께 저장합니다.",
    description: "제목, 아티스트, 앨범 커버를 포함한 MP3 파일을 생성합니다.",
    submitLabel: "노래 MP3 추출 시작",
    doneLabel: "노래 MP3 추출이 완료되었습니다.",
  },
  video: {
    label: "영상 추출",
    title: "선택한 화질의 영상을 내려받습니다.",
    description: "360p부터 8K까지 선택할 수 있고 필요한 구간만 잘라낼 수 있습니다.",
    submitLabel: "영상 추출 시작",
    doneLabel: "영상 추출이 완료되었습니다.",
  },
  subtitle: {
    label: "자막 추출",
    title: "YouTube 자막을 받거나 Whisper로 로컬 SRT를 생성합니다.",
    description: "Whisper 로컬 생성은 YouTube 링크 또는 업로드한 오디오 파일 모두 지원합니다.",
    submitLabel: "자막 추출 시작",
    doneLabel: "자막 추출이 완료되었습니다.",
  },
  batch: {
    label: "배치 다운로드",
    title: "재생목록 또는 채널 전체를 한 번에 처리합니다.",
    description: "선택한 작업을 모든 항목에 적용하고 결과를 ZIP으로 묶어 제공합니다.",
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
const ACTIVE_JOB_STORAGE_KEY = "ytme-active-job";
const COLAB_HOME_URL = "https://colab.research.google.com/";
const COLAB_NOTEBOOK_URL = "/api/subtitles/colab/notebook";
let activeJobRestorePromise = null;
let busyState = false;
let currentColabJob = null;

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

function saveActiveJob(jobId, fallbackName, overrides = {}) {
  window.localStorage.setItem(
    ACTIVE_JOB_STORAGE_KEY,
    JSON.stringify({
      jobId,
      fallbackName,
      mode: currentMode,
      savedAt: Date.now(),
      subtitleEngine: subtitleEngineSelect.value,
      subtitleSource: subtitleSourceSelect.value,
      whisperRuntime: getEffectiveWhisperRuntime(),
      ...overrides,
    }),
  );
}

function loadActiveJob() {
  try {
    const raw = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch (error) {
    console.error(error);
    window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    return null;
  }
}

function clearActiveJob() {
  window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
}

function applyActiveJobSelections(activeJob) {
  if (typeof activeJob?.mode === "string" && activeJob.mode in MODE_CONFIG) {
    currentMode = activeJob.mode;
  }

  if (typeof activeJob?.subtitleEngine === "string") {
    subtitleEngineSelect.value = activeJob.subtitleEngine;
  }

  if (typeof activeJob?.subtitleSource === "string") {
    subtitleSourceSelect.value = activeJob.subtitleSource;
  }

  if (activeJob?.whisperRuntime === "local" || activeJob?.whisperRuntime === "colab") {
    whisperRuntimeSelect.value = activeJob.whisperRuntime;
  }
}

function setBusy(isBusy) {
  busyState = isBusy;
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

  if (!isBusy) {
    syncColabUi();
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
  progressMessage.textContent = message || "작업이 진행 중입니다.";
  progressTitle.textContent = currentMode === "batch" ? "배치 작업 진행률" : `${MODE_CONFIG[currentMode].label} 진행률`;
  setBatchSummary(details);
}

function syncSubmitButtonLabel() {
  if (currentMode === "batch") {
    submitButton.textContent = `${BATCH_MODE_LABELS[batchModeSelect.value]} 배치 다운로드 시작`;
    return;
  }

  submitButton.textContent = isColabUploadMode() ? "Colab 패키지 만들기" : MODE_CONFIG[currentMode].submitLabel;
}

function resetProgress() {
  progressShell.classList.add("hidden");
  progressShell.dataset.state = "idle";
  progressShell.setAttribute("aria-hidden", "true");
  progressFill.style.width = "0%";
  progressLabel.textContent = "0%";
  progressTrack.setAttribute("aria-valuenow", "0");
  progressMessage.textContent = "작업을 준비하고 있습니다.";
  setBatchSummary({});
}

function getEffectiveSubtitleLanguage() {
  if (subtitleLanguageSelect.value === "custom") {
    return String(subtitleLanguageCustomInput.value || "").trim();
  }
  return subtitleLanguageSelect.value;
}

function getEffectiveSubtitleFormat() {
  return subtitleFormatSelect.value || "timestamped";
}

function getEffectiveWhisperDevice() {
  return whisperDeviceSelect.value || "auto";
}

function getEffectiveWhisperRuntime() {
  return whisperRuntimeSelect.value || "local";
}

function isWhisperSubtitleMode() {
  return currentMode === "subtitle" && subtitleEngineSelect.value === "whisper";
}

function isUploadWhisperMode() {
  return isWhisperSubtitleMode() && subtitleSourceSelect.value === "audio_file";
}

function isColabUploadMode() {
  return isUploadWhisperMode() && getEffectiveWhisperRuntime() === "colab";
}

function isPendingColabActiveJob(activeJob) {
  return (
    Boolean(activeJob?.jobId) &&
    activeJob?.mode === "subtitle" &&
    activeJob?.subtitleEngine === "whisper" &&
    activeJob?.subtitleSource === "audio_file" &&
    activeJob?.whisperRuntime === "colab"
  );
}

function buildColabJobSnapshot(job, fallbackName = "") {
  const details = job?.details || {};
  return {
    jobId: job?.jobId || "",
    status: job?.status || "waiting_for_colab",
    progress: Number(job?.progress || 0),
    message: job?.message || "",
    error: job?.error || "",
    details,
    fallbackName: job?.filename || fallbackName || details.colabResultName || "uploaded-whisper-subtitles.srt",
    downloadUrl: job?.downloadUrl || "",
  };
}

function setCurrentColabJob(job) {
  currentColabJob = job;
  syncColabUi();
}

function getColabStatusLabel(status) {
  switch (status) {
    case "waiting_for_colab":
      return "번들 준비됨";
    case "importing_result":
      return "가져오는 중";
    case "completed":
      return "완료";
    case "failed":
      return "실패";
    case "processing":
      return "준비 중";
    default:
      return "대기";
  }
}

function getColabPanelCopy(job) {
  if (!job || !job.jobId) {
    return "먼저 제출해서 Colab 번들을 만드세요. 그다음 Colab에서 노트북을 실행하고, 번들 ZIP을 업로드한 뒤 결과 ZIP을 다시 가져오면 됩니다.";
  }

  if (job.status === "waiting_for_colab") {
    return job.message || "번들이 준비되었습니다. 번들을 내려받아 Colab 노트북을 실행하고, 작업이 끝나면 결과 ZIP을 가져오세요.";
  }

  if (job.status === "importing_result") {
    return job.message || "Colab에서 받은 결과 ZIP을 가져오는 중입니다.";
  }

  if (job.status === "completed") {
    return job.message || "Colab 결과를 성공적으로 가져왔습니다. 자막 다운로드가 준비되었습니다.";
  }

  if (job.status === "failed") {
    return job.error || job.message || "Colab handoff 작업이 실패했습니다.";
  }

  return job.message || "Colab handoff 작업을 준비하는 중입니다.";
}

function syncColabUi() {
  const panelVisible = isColabUploadMode();
  colabPanel.classList.toggle("hidden", !panelVisible);
  if (!panelVisible) {
    return;
  }

  const details = currentColabJob?.details || {};
  const hasJob = Boolean(currentColabJob?.jobId);
  const status = currentColabJob?.status || "idle";
  const bundleUrl = details.bundleDownloadUrl || "";
  const bundleFilename = details.bundleFilename || "colab-job.zip";
  const resultFilename = details.colabResultName || "colab-result.zip";
  const resultUploadUrl = details.resultUploadUrl || "";

  colabStatusBadge.textContent = getColabStatusLabel(status);
  colabStatusBadge.dataset.state = status;
  colabPanelCopy.textContent = getColabPanelCopy(currentColabJob);
  colabJobId.textContent = hasJob ? currentColabJob.jobId : "아직 없음";
  colabBundleName.textContent = hasJob ? bundleFilename : "먼저 제출";
  colabResultName.textContent = resultFilename;
  colabPanelHelp.textContent = hasJob
    ? "수동 handoff 전용입니다. 번들과 노트북을 내려받아 Colab에서 실행한 뒤, 반환된 ZIP을 다시 가져오세요."
    : "수동 handoff 전용입니다. 노트북은 지금 내려받을 수 있지만, 번들 다운로드와 결과 가져오기는 제출 후에 활성화됩니다.";

  colabDownloadNotebookButton.disabled = busyState;
  colabOpenHomeButton.disabled = busyState;
  colabDownloadBundleButton.disabled = busyState || !hasJob || !bundleUrl || status === "completed";
  colabImportResultButton.disabled = busyState || !hasJob || !resultUploadUrl || status === "importing_result" || status === "completed";
}

function syncSubtitleLanguageUi() {
  const languageVisible =
    !subtitleLanguageField.classList.contains("hidden") && subtitleLanguageSelect.value === "custom";
  subtitleLanguageCustomField.classList.toggle("hidden", !languageVisible);
}

function syncSubtitleUi() {
  const isBatchSubtitle = currentMode === "batch" && batchModeSelect.value === "subtitle";
  const showEngine = currentMode === "subtitle";
  const showLanguage = currentMode === "subtitle" || isBatchSubtitle;
  const showFormat = currentMode === "subtitle" || isBatchSubtitle;
  const showWhisperOptions = isWhisperSubtitleMode();
  const showUploadSource = showWhisperOptions;
  const showUploadField = isUploadWhisperMode();
  const showRuntimeField = showUploadField;

  subtitleEngineField.classList.toggle("hidden", !showEngine);
  subtitleSourceField.classList.toggle("hidden", !showUploadSource);
  subtitleLanguageField.classList.toggle("hidden", !showLanguage);
  subtitleFormatField.classList.toggle("hidden", !showFormat);
  whisperModelField.classList.toggle("hidden", !showWhisperOptions);
  whisperDeviceField.classList.toggle("hidden", !showWhisperOptions);
  whisperRuntimeField.classList.toggle("hidden", !showRuntimeField);
  audioUploadField.classList.toggle("hidden", !showUploadField);
  audioUploadHelp.classList.toggle("hidden", !showUploadField);
  vadFilterField.classList.toggle("hidden", !showWhisperOptions);
  linkSection.classList.toggle("hidden", showUploadField);

  urlInput.required = !showUploadField;
  audioFileInput.required = showUploadField;

  if (showWhisperOptions && showUploadField) {
    subtitleEngineHelp.classList.remove("hidden");
    subtitleEngineHelp.textContent =
      getEffectiveWhisperRuntime() === "colab"
        ? "Google Colab 수동 handoff 모드입니다. 제출 후 번들을 내려받아 Colab 노트북에서 실행하고, 완료된 결과 ZIP을 다시 가져오세요."
        : "업로드한 오디오 파일을 로컬 faster-whisper로 전사해 SRT를 생성합니다.";
  } else if (showWhisperOptions) {
    subtitleEngineHelp.classList.remove("hidden");
    subtitleEngineHelp.textContent = "긴 영상은 base, 품질과 속도 균형은 small, 고사양 PC는 large-v3-turbo를 권장합니다. 선택한 Whisper 모델은 첫 실행 시 1회 다운로드 후 로컬에 캐시됩니다.";
  } else if (isBatchSubtitle) {
    subtitleEngineHelp.classList.remove("hidden");
    subtitleEngineHelp.textContent = "배치 자막은 현재 YouTube 자막 다운로드만 지원합니다.";
  } else if (showEngine) {
    subtitleEngineHelp.classList.remove("hidden");
    subtitleEngineHelp.textContent = "YouTube 제공 자막이 없으면 Whisper 로컬 생성을 선택하세요.";
  } else {
    subtitleEngineHelp.classList.add("hidden");
    subtitleEngineHelp.textContent = "";
  }

  syncSubtitleLanguageUi();
  syncSubmitButtonLabel();
  syncColabUi();
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
      ? `${MODE_CONFIG.batch.description} 현재 선택: ${BATCH_MODE_LABELS[effectiveBatchMode]}.`
      : MODE_CONFIG[currentMode].description;

  batchModeField.classList.toggle("hidden", currentMode !== "batch");
  audioFormatField.classList.toggle("hidden", !(currentMode === "audio" || (currentMode === "batch" && effectiveMode === "audio")));
  videoQualityField.classList.toggle("hidden", !(currentMode === "video" || (currentMode === "batch" && effectiveMode === "video")));

  if (currentMode === "batch" && effectiveMode === "subtitle") {
    subtitleEngineSelect.value = "youtube";
  }

  rangeHelp.textContent =
    currentMode === "batch"
      ? "시간을 비워 두면 전체 구간을 처리합니다. 배치 다운로드에서는 같은 시간 범위를 모든 항목에 적용합니다."
      : "시간을 비워 두면 전체 구간을 처리합니다.";

  submitButton.textContent =
    currentMode === "batch"
      ? `${BATCH_MODE_LABELS[effectiveBatchMode]} 배치 다운로드 시작`
      : MODE_CONFIG[currentMode].submitLabel;

  syncSubtitleUi();
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
        throw new Error("선택한 폴더에 대한 쓰기 권한이 필요합니다.");
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
    return "폴더 저장에 실패하여 브라우저 다운로드로 전환했습니다.";
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

function buildUploadPayload() {
  const formData = new FormData();
  const audioFile = audioFileInput.files && audioFileInput.files[0];
  const whisperRuntime = getEffectiveWhisperRuntime();
  const useColabRuntime = isColabUploadMode();

  if (!audioFile) {
    throw new Error("업로드할 오디오 파일을 선택하세요.");
  }

  formData.append("file", audioFile);
  formData.append("whisperModel", whisperModelSelect.value);
  formData.append("whisperDevice", getEffectiveWhisperDevice());
  formData.append("subtitleLanguage", getEffectiveSubtitleLanguage() || "ko");
  formData.append("subtitleFormat", getEffectiveSubtitleFormat());
  formData.append("vadFilter", String(Boolean(vadFilterCheckbox.checked)));

  const startTime = String(startTimeInput.value || "").trim();
  const endTime = String(endTimeInput.value || "").trim();
  if (startTime) {
    formData.append("startTime", startTime);
  }
  if (endTime) {
    formData.append("endTime", endTime);
  }

  return {
    uploadMode: true,
    manualHandoff: useColabRuntime,
    whisperRuntime,
    endpoint: useColabRuntime ? "/api/subtitles/upload/colab/jobs" : "/api/subtitles/upload/jobs",
    fallbackName: getEffectiveSubtitleFormat() === "clean" ? "uploaded-whisper-subtitles.txt" : "uploaded-whisper-subtitles.srt",
    body: formData,
  };
}

function buildJsonPayload() {
  const commonPayload = {
    taskType: currentMode,
    url: String(urlInput.value || "").trim(),
    startTime: String(startTimeInput.value || "").trim() || null,
    endTime: String(endTimeInput.value || "").trim() || null,
  };

  if (currentMode === "audio") {
    return {
      uploadMode: false,
      endpoint: "/api/jobs",
      fallbackName: `youtube-audio.${audioFormatSelect.value}`,
      body: JSON.stringify({
        ...commonPayload,
        audioFormat: audioFormatSelect.value,
      }),
    };
  }

  if (currentMode === "song_mp3") {
    return {
      uploadMode: false,
      endpoint: "/api/jobs",
      fallbackName: "youtube-song.mp3",
      body: JSON.stringify(commonPayload),
    };
  }

  if (currentMode === "video") {
    return {
      uploadMode: false,
      endpoint: "/api/jobs",
      fallbackName: "youtube-video.mp4",
      body: JSON.stringify({
        ...commonPayload,
        videoQuality: videoQualitySelect.value,
      }),
    };
  }

  if (currentMode === "subtitle") {
    const subtitleEngine = subtitleEngineSelect.value;
    const subtitleFormat = getEffectiveSubtitleFormat();
    return {
      uploadMode: false,
      endpoint: "/api/jobs",
      fallbackName:
        subtitleFormat === "clean"
          ? subtitleEngine === "whisper"
            ? "youtube-whisper-subtitles.txt"
            : "youtube-subtitles.txt"
          : subtitleEngine === "whisper"
            ? "youtube-whisper-subtitles.srt"
            : "youtube-subtitles.srt",
      body: JSON.stringify({
        ...commonPayload,
        subtitleEngine,
        subtitleFormat,
        subtitleLanguage: getEffectiveSubtitleLanguage() || "ko",
        whisperModel: whisperModelSelect.value,
        whisperDevice: getEffectiveWhisperDevice(),
        vadFilter: Boolean(vadFilterCheckbox.checked),
      }),
    };
  }

  const batchMode = batchModeSelect.value;
  return {
    uploadMode: false,
    endpoint: "/api/jobs",
    fallbackName: `youtube-batch-${batchMode}.zip`,
    body: JSON.stringify({
      ...commonPayload,
      taskType: "batch",
      batchMode,
      audioFormat: audioFormatSelect.value,
      videoQuality: videoQualitySelect.value,
      subtitleFormat: getEffectiveSubtitleFormat(),
      subtitleLanguage: getEffectiveSubtitleLanguage() || "ko",
      subtitleEngine: "youtube",
      whisperModel: whisperModelSelect.value,
      whisperDevice: getEffectiveWhisperDevice(),
      vadFilter: Boolean(vadFilterCheckbox.checked),
    }),
  };
}

function buildRequestConfig() {
  if (isUploadWhisperMode()) {
    return buildUploadPayload();
  }
  return buildJsonPayload();
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

async function fetchJobSnapshot(jobId, fallbackName = "download.bin") {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    if (response.status === 404) {
      clearActiveJob();
    }
    throw new Error(await readErrorMessage(response, "작업 상태를 조회하지 못했습니다."));
  }

  return buildColabJobSnapshot(await response.json(), fallbackName);
}

async function handleColabNotebookDownload() {
  setBusy(true);
  try {
    const result = await fetchDownload(COLAB_NOTEBOOK_URL, "whisper_transcribe.ipynb");
    setStatus(`Colab 노트북을 다운로드했습니다. ${result.saveMessage}`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Colab 노트북을 다운로드하지 못했습니다.";
    setStatus(message, "error");
  } finally {
    setBusy(false);
  }
}

async function handleColabBundleDownload() {
  if (!currentColabJob?.details?.bundleDownloadUrl) {
    setStatus("먼저 Colab 작업을 만들어야 번들을 내려받을 수 있습니다.", "error");
    return;
  }

  setBusy(true);
  try {
    const result = await fetchDownload(
      currentColabJob.details.bundleDownloadUrl,
      currentColabJob.details.bundleFilename || "colab-job.zip",
    );
    setStatus(`Colab 번들을 다운로드했습니다. ${result.saveMessage}`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Colab 번들을 다운로드하지 못했습니다.";
    setStatus(message, "error");
  } finally {
    setBusy(false);
  }
}

function handleOpenColabHome() {
  const destination = currentColabJob?.details?.colabHomeUrl || COLAB_HOME_URL;
  window.open(destination, "_blank", "noopener,noreferrer");
  setStatus("Google Colab을 새 탭에서 열었습니다.", "idle");
}

function handleColabImportClick() {
  if (!currentColabJob?.details?.resultUploadUrl) {
    setStatus("먼저 Colab 작업을 만든 뒤 결과 ZIP을 가져오세요.", "error");
    return;
  }

  colabResultFileInput.value = "";
  colabResultFileInput.click();
}

async function importColabResultFile(file) {
  if (!currentColabJob?.jobId || !currentColabJob?.details?.resultUploadUrl) {
    throw new Error("가져올 수 있는 Colab 작업이 없습니다.");
  }

  const resultUploadUrl = currentColabJob.details.resultUploadUrl;
  const jobId = currentColabJob.jobId;
  const fallbackName = currentColabJob.fallbackName;
  const formData = new FormData();
  formData.append("file", file);

  const importingJob = {
    ...currentColabJob,
    status: "importing_result",
    progress: Math.max(90, Number(currentColabJob.progress || 0)),
    message: "Colab 결과 패키지를 가져오는 중입니다.",
  };

  setCurrentColabJob(importingJob);
  setBusy(true);
  setProgress(importingJob.progress, importingJob.message, importingJob.status, importingJob.details || {});
  setStatus("Colab 결과 ZIP을 가져오는 중입니다.", "busy");

  try {
    const response = await fetch(resultUploadUrl, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const message = await readErrorMessage(response, "Colab 결과 ZIP을 가져오지 못했습니다.");
      try {
        const restoredJob = await fetchJobSnapshot(jobId, fallbackName);
        setCurrentColabJob(restoredJob);
        setProgress(restoredJob.progress, restoredJob.message || message, "error", restoredJob.details || {});
      } catch (refreshError) {
        console.error(refreshError);
      }
      throw new Error(message);
    }

    const completedJob = buildColabJobSnapshot(await response.json(), fallbackName);
    setCurrentColabJob(completedJob);

    const result = await fetchDownload(completedJob.downloadUrl, completedJob.fallbackName);
    clearActiveJob();
    setProgress(100, completedJob.message || "Colab 자막 가져오기가 완료되었습니다.", "success", completedJob.details || {});
    setStatus(`Colab 결과를 가져왔습니다. ${result.saveMessage}`, "success");
  } finally {
    setBusy(false);
  }
}

async function handleColabResultSelection(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }

  try {
    await importColabResultFile(file);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Colab 결과 ZIP을 가져오지 못했습니다.";
    setStatus(message, "error");
  } finally {
    colabResultFileInput.value = "";
  }
}

async function waitForJob(jobId, fallbackName) {
  let reconnectAttempts = 0;

  while (true) {
    let response;
    try {
      response = await fetch(`/api/jobs/${jobId}`);
      reconnectAttempts = 0;
    } catch (error) {
      reconnectAttempts += 1;
      setProgress(
        Number(progressLabel.textContent.replace("%", "")) || 0,
        "로컬 앱에 다시 연결하는 중입니다. 앱이 다시 켜지면 자동으로 이어집니다.",
        "busy",
      );
      if (reconnectAttempts >= 300) {
        throw error;
      }
      await sleep(2000);
      continue;
    }
    if (!response.ok) {
      if (response.status === 404) {
        clearActiveJob();
      }
      throw new Error(await readErrorMessage(response, "작업 상태를 조회하지 못했습니다."));
    }

    const job = await response.json();
    setProgress(job.progress || 0, job.message || "처리 중입니다.", job.status || "processing", job.details || {});

    if (job.status === "failed") {
      clearActiveJob();
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

async function createJob(config) {
  if (config.uploadMode) {
    return fetch(config.endpoint, {
      method: "POST",
      body: config.body,
    });
  }

  return fetch(config.endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: config.body,
  });
}

async function handleSubmit(event) {
  event.preventDefault();

  const config = buildRequestConfig();
  const useColabRuntime = isColabUploadMode();
  const activeJob = loadActiveJob();
  if (useColabRuntime && isPendingColabActiveJob(activeJob)) {
    const shouldReplace = window.confirm(
      "이 브라우저에 아직 끝나지 않은 Colab handoff가 있습니다. 새 작업을 시작하면 이 저장된 handoff가 대체됩니다. 계속할까요?",
    );
    if (!shouldReplace) {
      return;
    }
  }

  clearActiveJob();
  if (useColabRuntime) {
    setCurrentColabJob(null);
  }
  setBusy(true);
  setProgress(0, "작업을 준비하고 있습니다.", "busy", currentMode === "batch" ? { total: 0, completed: 0, failed: 0 } : {});
  setStatus(`${MODE_CONFIG[currentMode].label} 작업을 시작합니다.`, "busy");

  try {
    const createResponse = await createJob(config);
    if (!createResponse.ok) {
      throw new Error(await readErrorMessage(createResponse, "작업을 시작하지 못했습니다."));
    }

    const createdJob = await createResponse.json();
    saveActiveJob(createdJob.jobId, config.fallbackName, {
      subtitleEngine: subtitleEngineSelect.value,
      subtitleSource: subtitleSourceSelect.value,
      whisperRuntime: config.whisperRuntime || "local",
    });
    setProgress(
      createdJob.progress || 0,
      createdJob.message || "작업을 준비하고 있습니다.",
      createdJob.status || "queued",
      createdJob.details || {},
    );

    if (useColabRuntime || createdJob.status === "waiting_for_colab") {
      const colabJob = buildColabJobSnapshot(
        createdJob,
        createdJob?.details?.colabResultName || config.fallbackName || "uploaded-whisper-subtitles.srt",
      );
      setCurrentColabJob(colabJob);
      setStatus(
        createdJob.message || "Colab 패키지가 준비되었습니다. 번들을 내려받아 노트북을 실행한 뒤 결과 ZIP을 가져오세요.",
        "success",
      );
      return;
    }

    const completedJob = await waitForJob(createdJob.jobId, config.fallbackName);
    const result = await fetchDownload(completedJob.downloadUrl, completedJob.filename);
    clearActiveJob();
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

async function restoreActiveJob() {
  if (activeJobRestorePromise) {
    return activeJobRestorePromise;
  }

  const activeJob = loadActiveJob();
  if (!activeJob || !activeJob.jobId) {
    return;
  }

  activeJobRestorePromise = (async () => {
    applyActiveJobSelections(activeJob);
    syncModeUi();

    setBusy(true);
    setProgress(0, "이전 작업에 다시 연결하는 중입니다.", "busy");
    setStatus("이전 작업에 다시 연결하는 중입니다.", "busy");

    try {
      if (isPendingColabActiveJob(activeJob)) {
        const restoredJob = await fetchJobSnapshot(activeJob.jobId, activeJob.fallbackName || "uploaded-whisper-subtitles.srt");
        setCurrentColabJob(restoredJob);

        if (restoredJob.status === "completed" && restoredJob.downloadUrl) {
          const result = await fetchDownload(restoredJob.downloadUrl, restoredJob.fallbackName);
          clearActiveJob();
          setProgress(100, restoredJob.message || "Colab 자막 가져오기가 완료되었습니다.", "success", restoredJob.details || {});
          setStatus(`Colab 결과를 가져왔습니다. ${result.saveMessage}`, "success");
          return;
        }

        if (restoredJob.status === "failed") {
          clearActiveJob();
          setProgress(restoredJob.progress, restoredJob.error || restoredJob.message || "작업이 실패했습니다.", "error", restoredJob.details || {});
          setStatus(restoredJob.error || restoredJob.message || "작업이 실패했습니다.", "error");
          return;
        }

        setProgress(
          restoredJob.progress,
          restoredJob.message || "Colab 패키지가 준비되었습니다.",
          restoredJob.status || "waiting_for_colab",
          restoredJob.details || {},
        );
        setStatus(restoredJob.message || "Colab 패키지가 준비되었습니다. 수동 단계를 계속 진행하세요.", "idle");
        return;
      }

      const completedJob = await waitForJob(activeJob.jobId, activeJob.fallbackName || "download.bin");
      const result = await fetchDownload(completedJob.downloadUrl, completedJob.filename);
      clearActiveJob();
      setProgress(100, completedJob.message || MODE_CONFIG[currentMode].doneLabel, "success", completedJob.details || {});
      setStatus(`${MODE_CONFIG[currentMode].doneLabel} ${result.saveMessage}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "작업이 실패했습니다.";
      setProgress(Number(progressLabel.textContent.replace("%", "")) || 0, message, "error");
      setStatus(message, "error");
    } finally {
      setBusy(false);
      activeJobRestorePromise = null;
    }
  })();

  return activeJobRestorePromise;
}

if (typeof window.showDirectoryPicker !== "function") {
  folderButton.disabled = true;
  folderHelp.textContent =
    "Chrome 또는 Edge에서는 폴더 직접 저장을 지원합니다. 다른 브라우저에서는 기본 다운로드 폴더를 사용합니다.";
}

for (const button of modeButtons) {
  button.addEventListener("click", () => {
    currentMode = button.dataset.mode || "audio";
    syncModeUi();
    resetProgress();
    setStatus("준비되었습니다.", "idle");
  });
}

subtitleEngineSelect.addEventListener("change", syncSubtitleUi);
subtitleSourceSelect.addEventListener("change", syncSubtitleUi);
subtitleLanguageSelect.addEventListener("change", syncSubtitleLanguageUi);
whisperRuntimeSelect.addEventListener("change", () => {
  if (getEffectiveWhisperRuntime() === "colab") {
    if (whisperModelSelect.value === "base") {
      whisperModelSelect.value = "large-v3-turbo";
    }
    if (whisperDeviceSelect.value === "auto") {
      whisperDeviceSelect.value = "cuda";
    }
  }
  syncSubtitleUi();
});
batchModeSelect.addEventListener("change", syncModeUi);
folderButton.addEventListener("click", handleFolderPick);
themeToggle.addEventListener("click", toggleTheme);
colabDownloadBundleButton.addEventListener("click", handleColabBundleDownload);
colabDownloadNotebookButton.addEventListener("click", handleColabNotebookDownload);
colabOpenHomeButton.addEventListener("click", handleOpenColabHome);
colabImportResultButton.addEventListener("click", handleColabImportClick);
colabResultFileInput.addEventListener("change", handleColabResultSelection);
form.addEventListener("submit", handleSubmit);

initializeTheme();
syncModeUi();
restoreActiveJob();
