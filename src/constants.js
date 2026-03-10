const AUDIO_FORMATS = {
  mp3: {
    extension: "mp3",
    mimeType: "audio/mpeg",
    ffmpegArgs: ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"],
  },
  m4a: {
    extension: "m4a",
    mimeType: "audio/mp4",
    ffmpegArgs: ["-vn", "-c:a", "aac", "-b:a", "192k"],
  },
  wav: {
    extension: "wav",
    mimeType: "audio/wav",
    ffmpegArgs: ["-vn", "-c:a", "pcm_s16le"],
  },
  opus: {
    extension: "opus",
    mimeType: "audio/ogg",
    ffmpegArgs: ["-vn", "-c:a", "libopus", "-b:a", "160k"],
  },
};

module.exports = {
  AUDIO_FORMATS,
};

