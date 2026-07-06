# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development

This app runs in Docker. There is no local dev server setup — all development is done by rebuilding the container:

```bash
docker build -t mars:latest .
cp docker-compose.example docker-compose.yml  # first time only, then edit paths
docker-compose up -d
```

The Flask app is served on port 5000; noVNC on port 6080.

No test framework or linter is configured.

## Architecture

MARS is a self-hosted media archiving system. It spins up a headless Chrome browser inside Docker, lets users navigate to sites (via noVNC), detects video streams via Chrome DevTools Protocol (CDP), and downloads them with FFmpeg.

**Backend**: Python/Flask, layered as:

- `app/routes/` — Flask blueprints. One per concern: `browser_routes.py`, `download_routes.py`, `scheduler_routes.py`, `events_routes.py` (SSE).
- `app/services/` — Orchestration. `browser_service.py` (single-Chrome launch queue, manual-session tracking), `download_service.py` (FFmpeg download queue, thumbnails, history).
- `app/models/stream_detector/` — `StreamDetector` class composed from mixins: `cdp_mixin.py` (CDP WebSocket events), `network_monitor_mixin.py` (performance-log polling backup), `stream_parser_mixin.py` (stream classification + detection dedup), `stream_matcher_mixin.py` (resolution/framerate matching), `download_handler_mixin.py` (filename generation, download kickoff).
- `app/utils/` — `playlist_parser.py` (HLS master playlists), `metadata_extractor.py` (ffprobe), `thumbnail_generator.py` (ffmpeg frames).
- `app/scheduler.py` — Scheduling engine. Daily/weekly repeats, auto-resume on stream crashes, auto-pause of schedules during manual sessions (`auto_paused` can hit disk mid-session but is stripped on load, so it never survives a restart).

Real-time download progress is streamed to the frontend via Server-Sent Events (SSE) from `events_routes.py`.

**Frontend**: Vanilla JS (no framework). Files in `app/static/js/`:

- `state.js` — Single global `AppState` object shared across modules via `window.AppState`.
- `init.js` — DOMContentLoaded entry point; starts polling intervals for active downloads (1 s), schedules (10 s), and completed downloads (10 s).
- `ui.js`, `schedules.js`, `downloads-browser.js`, `validation.js`, `timepicker.js` — Feature-specific modules. Dynamic values (filenames, stream names, URLs) must be set via DOM APIs (`textContent`, `addEventListener`), never interpolated into HTML strings.

The single-page UI is `app/templates/index.html` (rendered by Flask, but uses no template variables beyond `url_for`).

**Infrastructure inside the container** (managed by supervisord):
- `Xvfb` — Virtual display for Chrome
- `x11vnc` + `noVNC` — Browser-accessible VNC
- Flask app via `python -u -m app.app`

**Three download modes**:
1. Direct URL download (`.m3u8`, `.mpd`, `.mp4`)
2. Browser mode — navigate interactively, CDP detects streams automatically
3. Scheduled downloads — time-windowed, repeatable, auto-resuming
