# Free business video generator (Sora API example)

This is a tiny starter app that gives your business a web form for generating videos from text prompts using a Sora-compatible API.

## What you get

- A lightweight Express backend that calls `POST /videos/generations`
- A no-build frontend form for prompt, duration, and aspect ratio
- A safe starting point you can deploy cheaply (Render, Railway, Fly, etc.)

## Setup

From the repo root:

```bash
cd docs/examples/sora-video-app
export SORA_API_KEY="your_api_key"
# Optional overrides:
# export SORA_API_BASE="https://api.openai.com/v1"
# export SORA_MODEL="sora-1"
node server.mjs
```

Open <http://localhost:8787>.

## Notes about "free"

- Most video APIs are paid. You can still keep costs low by:
  - limiting duration (`3-8s`)
  - adding daily generation caps per user
  - requiring sign-in before generation
- The frontend is static and the server is tiny, so hosting can be free/near-free.

## Next steps for production

1. Add auth + rate limits per account
2. Save request IDs/status in a database
3. Add webhook polling for job completion
4. Store generated files in your own object storage/CDN
