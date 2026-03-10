const { createApp } = require("./app");
const { ensureYtDlpBinary } = require("./yt-dlp");

const port = Number(process.env.PORT) || 3000;
const app = createApp();

app.listen(port, () => {
  console.log(`YouTube Audio Extractor listening on http://localhost:${port}`);

  ensureYtDlpBinary()
    .then(() => {
      console.log("yt-dlp is ready.");
    })
    .catch((error) => {
      console.warn(`yt-dlp setup failed: ${error.message}`);
    });
});

