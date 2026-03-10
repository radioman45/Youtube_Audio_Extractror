const test = require("node:test");
const assert = require("node:assert/strict");
const { createServer } = require("node:http");
const { createApp } = require("../src/app");
const { buildFfmpegArgs } = require("../src/extractor");
const { parseFlexibleTime } = require("../src/time");
const { isYouTubeUrl, parseExtractionRequest } = require("../src/validation");

test("parseFlexibleTime supports seconds and clock notation", () => {
  assert.equal(parseFlexibleTime("90"), 90);
  assert.equal(parseFlexibleTime("01:30"), 90);
  assert.equal(parseFlexibleTime("00:01:30"), 90);
  assert.equal(parseFlexibleTime(""), null);
});

test("parseExtractionRequest validates range ordering", () => {
  assert.throws(
    () =>
      parseExtractionRequest({
        url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        audioFormat: "mp3",
        startTime: "02:00",
        endTime: "01:00",
      }),
    /종료 시간/,
  );
});

test("isYouTubeUrl accepts youtube domains", () => {
  assert.equal(isYouTubeUrl("https://youtu.be/dQw4w9WgXcQ"), true);
  assert.equal(isYouTubeUrl("https://example.com/video"), false);
});

test("buildFfmpegArgs adds clip duration when end time exists", () => {
  const args = buildFfmpegArgs("source.webm", "clip.mp3", {
    audioFormat: "mp3",
    startSeconds: 10,
    endSeconds: 25,
  });

  assert.deepEqual(args.slice(0, 8), [
    "-hide_banner",
    "-loglevel",
    "error",
    "-y",
    "-ss",
    "10",
    "-i",
    "source.webm",
  ]);
  assert.ok(args.includes("-t"));
  assert.ok(args.includes("15"));
});

test("health endpoint responds with JSON", async () => {
  const app = createApp();
  const server = createServer(app);

  await new Promise((resolve) => server.listen(0, resolve));

  const address = server.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/api/health`);
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.ok, true);
  assert.deepEqual(payload.formats, ["mp3", "m4a", "wav", "opus"]);

  await new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }

      resolve();
    });
  });
});

