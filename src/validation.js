const { z } = require("zod");
const { AUDIO_FORMATS } = require("./constants");
const { parseFlexibleTime } = require("./time");

class InputError extends Error {}

function isYouTubeUrl(value) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.replace(/^www\./, "");
    return ["youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"].includes(host);
  } catch {
    return false;
  }
}

const extractionSchema = z.object({
  url: z
    .string()
    .trim()
    .min(1, "유튜브 링크를 입력해 주세요.")
    .refine(isYouTubeUrl, "유효한 유튜브 링크만 지원합니다."),
  audioFormat: z.enum(Object.keys(AUDIO_FORMATS), {
    error: () => ({ message: "지원하지 않는 오디오 형식입니다." }),
  }),
  startTime: z.string().trim().optional().default(""),
  endTime: z.string().trim().optional().default(""),
});

function parseExtractionRequest(payload) {
  const parsed = extractionSchema.parse(payload);
  let startSeconds = null;
  let endSeconds = null;

  try {
    startSeconds = parseFlexibleTime(parsed.startTime);
    endSeconds = parseFlexibleTime(parsed.endTime);
  } catch (error) {
    throw new InputError(error.message);
  }

  if (startSeconds !== null && endSeconds !== null && endSeconds <= startSeconds) {
    throw new InputError("종료 시간은 시작 시간보다 뒤여야 합니다.");
  }

  return {
    url: parsed.url,
    audioFormat: parsed.audioFormat,
    startTime: parsed.startTime,
    endTime: parsed.endTime,
    startSeconds,
    endSeconds,
    clipRequested: startSeconds !== null || endSeconds !== null,
  };
}

module.exports = {
  InputError,
  isYouTubeUrl,
  parseExtractionRequest,
};
