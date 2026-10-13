# Videogen Studio

A video creation and editing website built on **MoneyPrinterTurbo**. It reuses the
upstream script, caption, media-validation, queue, and rendering services, keeps
the MIT license, and adds a simplified studio and FreeLLMAPI configuration.
See [UPSTREAM.md](UPSTREAM.md) for the imported revision and attribution.

## Run

Requires Python 3.11 or later, `uv`, and FFmpeg / FFprobe with the `libx264` encoder
and `drawtext` filter. A GPU is not required. Install FFmpeg from your operating
system package manager when it is not already available.

```bash
cd /workspace/videogen
bash scripts/setup-studio.sh
bash scripts/start-studio.sh
```

The web server listens on port 8501 by default. `STUDIO_PORT` and `STUDIO_HOST`
can override it. For use only on your own machine, set `STUDIO_HOST=127.0.0.1`.
The original application remains available via `webui/Main.py`, `main.py`, and
`cli.py`; see [the upstream documentation](README-en.md).

## FreeLLMAPI

Copy `.env.example` to `.env` and configure these **server-side** variables, or
use the studio's API settings page:

- `FREELLM_API_KEY`: your provider key. Never commit it or paste it in chat.
- `FREELLM_BASE_URL`: your provider's OpenAI-compatible base URL. Use HTTPS for
  remote servers; HTTP is supported for localhost or literal loopback IPs.
- `FREELLM_MODEL`: the exact supported model ID.

The base URL must not include `/chat/completions`; the existing OpenAI SDK adds
that path. No FreeLLMAPI domain or model is invented by this project. The named
service's actual documentation and a working key are needed to verify its
compatibility. If the service uses a different protocol, its adapter will need
the documented request/response schema. The settings page has a connection test.
In cloud environments with restricted egress, allow the documented API hostname
in the environment's network settings. No guessed domain is added automatically.

Environment bindings take precedence over settings stored in `config.toml`.
`.env`, `config.toml`, uploaded media, and exports are ignored by Git. Keys saved
through the settings page stay in the private config file; they are not copied
into video metadata or sent as part of the browser page's initial state.

The `freellm` provider is also registered in the original MoneyPrinterTurbo LLM
settings, so its scripting pipeline can use the same gateway.

## A model installed on your PC

Run the studio on the **same PC** as the model's API server. Enable that server's
OpenAI-compatible API, copy the base URL it displays (including its port and API
prefix), and select the exact loaded model ID. Enter these and the existing API
key through API settings. Test the connection before writing a script.

On Windows, macOS, or Linux, install Python 3.11+ and FFmpeg/FFprobe, then open a
terminal in the extracted project folder. If needed, install uv with
`python -m pip install uv`. Run:

```bash
uv sync --frozen
uv run --frozen python scripts/start-studio-pc.py
```

This desktop launcher binds only to the local machine by default. The cloud
launcher remains `scripts/start-studio.sh`. The saved cloud configuration does
not start or install the model service on your personal PC.

Loopback HTTP is supported, including IPv4 and IPv6, and these local requests do
not pass through an external HTTP proxy. HTTPS certificate verification remains
enabled for remote providers. Public and LAN HTTP destinations are rejected.

The cloud workspace is a separate machine: its localhost cannot reach a model
running on your PC. Running both components on your PC requires no remote API
or cloud connection. The local model service must be running; simply installing
a model or possessing an API key does not establish a working API endpoint.

## What is free

The studio uses no paid video or image provider. Supply your own footage/photos
and a script, choose **No voice**, and it renders an MP4 and captions locally
without making LLM, stock-footage, voice, or paid-model requests. Optional
FreeLLMAPI requests are subject to your provider's pricing, free-tier allowance,
and rate limits. Optional Edge TTS uses Microsoft's online service and needs
network access. Hosting, storage, and CPU usage may have costs.

This creates narrated/captioned videos from footage, rather than generating
photorealistic footage from text. FreeLLMAPI is used for writing scripts.

## Edit videos

Upload a video or select an export from your library. Set a trim range, choose a
crop ratio, change playback speed, brightness, saturation, volume, and add a
text overlay. Export produces an H.264/AAC MP4 with the original preserved.
Exports are limited to five minutes per edit and 1920 pixels on the longest edge.
Input uploads reuse MoneyPrinterTurbo's file limits and full media validation.

The library lists generated and edited MP4s from persistent `storage/` folders.
Active rendering processes do not survive a server restart; completed exports do.
Long lines in text overlays should be manually wrapped with newlines.

This is a personal studio, following MoneyPrinterTurbo's global settings model.
Use an authenticated reverse proxy and appropriate storage isolation before
exposing it publicly or sharing it between unrelated users.

## Validate

```bash
.venv/bin/python -m pytest -q test/services/test_freellm.py test/services/test_studio_editor.py test/services/test_studio_ui.py
.venv/bin/python scripts/smoke-studio.py
```

The provider test exercises the real SDK using a simulated HTTP transport, with
no remote calls or credits consumed. The smoke test makes actual video files
and runs the original generation pipeline and the new FFmpeg editor locally.
Live FreeLLMAPI access must be checked separately after configuring the endpoint,
model and key. Cloud tasks already have isolated checkouts; reuse the existing
checkout rather than creating Git worktrees unless explicitly requested.
