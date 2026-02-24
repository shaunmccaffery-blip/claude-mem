import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const app = express();
const port = process.env.PORT || 8787;
const soraApiBase = process.env.SORA_API_BASE || "https://api.openai.com/v1";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

app.post("/api/generate-video", async (req, res) => {
  const { prompt, duration = 5, aspectRatio = "16:9" } = req.body || {};

  if (!prompt || typeof prompt !== "string") {
    return res.status(400).json({ error: "A prompt is required." });
  }

  if (!process.env.SORA_API_KEY) {
    return res.status(500).json({
      error: "Missing SORA_API_KEY. Add it to your environment before generating videos."
    });
  }

  try {
    const response = await fetch(`${soraApiBase}/videos/generations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${process.env.SORA_API_KEY}`
      },
      body: JSON.stringify({
        model: process.env.SORA_MODEL || "sora-1",
        prompt,
        duration,
        aspect_ratio: aspectRatio
      })
    });

    const payload = await response.json();

    if (!response.ok) {
      return res.status(response.status).json({
        error: payload?.error?.message || "Video request failed",
        details: payload
      });
    }

    return res.status(200).json({
      id: payload.id,
      status: payload.status || "queued",
      videoUrl: payload.output?.[0]?.url || null,
      raw: payload
    });
  } catch (error) {
    return res.status(502).json({
      error: "Unable to reach the video generation API.",
      details: error instanceof Error ? error.message : String(error)
    });
  }
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, apiBase: soraApiBase });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`Sora video app listening on http://localhost:${port}`);
});
