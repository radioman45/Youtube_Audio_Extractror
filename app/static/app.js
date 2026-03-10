const form = document.querySelector("#extract-form");
const submitButton = document.querySelector("#submit-button");
const statusText = document.querySelector("#status-text");
const folderButton = document.querySelector("#folder-button");
const folderDisplay = document.querySelector("#folder-display");
const folderHelp = document.querySelector("#folder-help");

const folderState = {
  handle: null,
};

function setStatus(message, state = "idle") {
  statusText.textContent = message;
  statusText.dataset.state = state;
}

function extractFilename(disposition, fallbackFormat) {
  if (!disposition) {
    return `youtube-audio.${fallbackFormat}`;
  }

  const utfMatch = disposition.match(/filename\*=utf-8''([^;]+)/i);
  if (utfMatch) {
    return decodeURIComponent(utfMatch[1]);
  }

  const asciiMatch = disposition.match(/filename="?([^"]+)"?/i);
  if (asciiMatch) {
    return asciiMatch[1];
  }

  return `youtube-audio.${fallbackFormat}`;
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
        throw new Error("선택한 폴더에 저장하려면 쓰기 권한이 필요합니다.");
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
    setStatus("이 브라우저는 폴더 직접 저장을 지원하지 않습니다.", "error");
    return;
  }

  try {
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    folderState.handle = handle;
    folderDisplay.textContent = handle.name;
    setStatus(`${handle.name} 폴더를 저장 위치로 선택했습니다.`, "success");
  } catch (error) {
    if (error?.name !== "AbortError") {
      console.error(error);
      setStatus("폴더 선택 중 오류가 발생했습니다.", "error");
    }
  }
}

async function handleSubmit(event) {
  event.preventDefault();

  const payload = {
    url: String(document.querySelector("#url").value || "").trim(),
    startTime: String(document.querySelector("#startTime").value || "").trim() || null,
    endTime: String(document.querySelector("#endTime").value || "").trim() || null,
    audioFormat: String(document.querySelector("#audioFormat").value || "mp3"),
  };

  submitButton.disabled = true;
  setStatus("오디오를 추출하고 있습니다. 링크 길이에 따라 시간이 조금 걸릴 수 있습니다.", "busy");

  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let detail = "추출 중 오류가 발생했습니다.";
      try {
        const errorBody = await response.json();
        detail = errorBody.detail || detail;
      } catch (error) {
        console.error(error);
      }
      throw new Error(detail);
    }

    const blob = await response.blob();
    const filename = extractFilename(response.headers.get("Content-Disposition"), payload.audioFormat);
    const saveMessage = await writeBlobToFolder(blob, filename);
    setStatus(`추출이 완료되었습니다. ${saveMessage}`, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "추출 중 오류가 발생했습니다.";
    setStatus(message, "error");
  } finally {
    submitButton.disabled = false;
  }
}

if (typeof window.showDirectoryPicker !== "function") {
  folderButton.disabled = true;
  folderHelp.textContent =
    "폴더 직접 저장은 Chrome 또는 Edge 같은 Chromium 브라우저에서 지원합니다. 지원되지 않으면 브라우저 기본 다운로드 폴더를 사용합니다.";
}

folderButton.addEventListener("click", handleFolderPick);
form.addEventListener("submit", handleSubmit);
