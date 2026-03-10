const form = document.querySelector("#extract-form");
const submitButton = document.querySelector("#submit-button");
const statusMessage = document.querySelector("#status-message");
const healthPill = document.querySelector("#health-pill");

function setStatus(message, type = "idle") {
  statusMessage.textContent = message;
  healthPill.classList.remove("ready", "error");

  if (type === "ready") {
    healthPill.textContent = "준비 완료";
    healthPill.classList.add("ready");
    return;
  }

  if (type === "error") {
    healthPill.textContent = "오류";
    healthPill.classList.add("error");
    return;
  }

  if (type === "working") {
    healthPill.textContent = "처리 중";
    return;
  }

  healthPill.textContent = "대기 중";
}

function getFileNameFromResponse(response) {
  const contentDisposition = response.headers.get("content-disposition");
  if (!contentDisposition) {
    return "youtube-audio";
  }

  const fileNameMatch = contentDisposition.match(/filename="([^"]+)"/i);
  return fileNameMatch?.[1] || "youtube-audio";
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();

    if (!data.ok) {
      throw new Error("서버 상태를 읽지 못했습니다.");
    }

    const readiness = data.ytDlpReady
      ? "추출 준비가 완료되었습니다."
      : "서버는 실행 중입니다. 첫 요청에서 yt-dlp를 자동 설치할 수 있습니다.";
    setStatus(readiness, "ready");
  } catch (error) {
    setStatus(error.message || "서버에 연결할 수 없습니다.", "error");
  }
}

async function handleSubmit(event) {
  event.preventDefault();

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  submitButton.disabled = true;
  setStatus(
    "오디오를 추출하고 있습니다. 첫 실행에서는 yt-dlp 다운로드 때문에 더 오래 걸릴 수 있습니다.",
    "working",
  );

  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.message || "오디오 추출에 실패했습니다.");
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = getFileNameFromResponse(response);
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);

    setStatus("다운로드를 시작했습니다. 다른 링크도 바로 추출할 수 있습니다.", "ready");
  } catch (error) {
    setStatus(error.message || "오디오 추출에 실패했습니다.", "error");
  } finally {
    submitButton.disabled = false;
  }
}

form.addEventListener("submit", handleSubmit);
checkHealth();

