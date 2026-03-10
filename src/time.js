function parseFlexibleTime(input) {
  if (input === undefined || input === null) {
    return null;
  }

  const value = String(input).trim();
  if (!value) {
    return null;
  }

  if (/^\d+$/.test(value)) {
    return Number(value);
  }

  const parts = value.split(":");
  if (parts.length < 2 || parts.length > 3) {
    throw new Error("시간 형식은 초, MM:SS 또는 HH:MM:SS 이어야 합니다.");
  }

  const numericParts = parts.map((part) => {
    if (!/^\d+$/.test(part)) {
      throw new Error("시간 형식은 숫자만 사용할 수 있습니다.");
    }
    return Number(part);
  });

  if (numericParts.slice(1).some((part) => part >= 60)) {
    throw new Error("분과 초는 60 미만이어야 합니다.");
  }

  if (parts.length === 2) {
    const [minutes, seconds] = numericParts;
    return minutes * 60 + seconds;
  }

  const [hours, minutes, seconds] = numericParts;
  return hours * 3600 + minutes * 60 + seconds;
}

function formatDurationLabel(seconds) {
  if (seconds === null || seconds === undefined) {
    return "전체 구간";
  }

  return `${seconds}초`;
}

module.exports = {
  formatDurationLabel,
  parseFlexibleTime,
};

