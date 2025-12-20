# Docker Video Downloader

> [!CAUTION]
> **LEGAL DISCLAIMER**: This software is intended for personal use only. Users must only download content they have the legal right to access and store (e.g., public domain content, content under free licenses, or content for which they have explicit permission). The developers of this software are not responsible for any misuse, copyright infringement, or violations of Terms of Service. Do not use this tool for commercial purposes or to distribute copyrighted material without permission.

A self-hosted video downloader designed for Docker environments that downloads videos and streams using FFmpeg with browser-based authentication support.

## Features

- **Dual Download Modes**
  - **Direct Download**: Download directly from URLs (.m3u8, .mpd, .mp4) with support for format conversion.
  - **Browser Mode**: Interactive Chrome browser to navigate, log in, and automatically detect video streams.

- **Format Conversion**
  - **Video**: MP4, MKV, WebM, MOV, AVI, FLV, WMV, TS
  - **Audio Extraction**: MP3, AAC, M4A, FLAC, WAV, OGG, OPUS, WMA

- **Advanced Browser Capabilities**
  - **Cookie Persistence**: Log in once, stay logged in specifically for sites requiring authentication.
  - **Stream Detection**: Automatically detects HLS, DASH, and progressive streams.
  - **Manual Control**: Options to select specific resolutions or streams if multiple are detected.
  - **Clear Cookies**: Built-in tool to clear browser data if needed.
  - **noVNC Integration**: View and interact with the browser directly within the web interface.

- **System**
  - **Background Processing**: Downloads run in the background with progress tracking.
  - **Thumbnail Generation**: Visual confirmation of the content being downloaded.
  - **Dockerized**: Optimized for containerized deployment with hardware acceleration support potential.

## Quick Start

### Deploy with Portainer (Recommended)

1. In Portainer, go to **Stacks** > **Add Stack**
2. Choose **Repository** deployment method
3. Enter your GitHub repository URL
4. Set the compose path: `docker-compose.yml`
5. Click **Deploy the stack**

### Manual Docker Compose

```bash
# Clone the repository
git clone <your-repo-url>
cd ffmepg-downloader

# Start the container
docker-compose up -d

# Check logs
docker-compose logs -f
```

## Access

- **Web Interface**: `http://your-server-ip:5000`
- **Internal VNC**: Accessed via the "View Browser" button in the web interface (port 6080 internally).

## Usage

### Direct Download Mode

1. Open the web interface.
2. Select **Direct Download** tab.
3. Paste a stream URL (e.g., `.m3u8` or `.mp4`).
4. (Optional) Enter a custom filename.
5. Select the **Output Format** (Video or Audio).
6. Click **Download**.

### Browser Mode (Find Link)

**First time on a new site:**

1. Select **Browser Mode** tab.
2. Enter the webpage URL (e.g., `https://videosite.com/watch/12345`).
3. Select desired **Output Format**.
4. Click **Launch Browser**.
5. The browser view will appear. **Log in** to the site if necessary.
6. Navigate to the video and play it.
7. The system will detect the stream and offer to download it.
8. Confirm the download (or it will auto-start if configured).

**Next time on the same site:**

1. Paste a new video URL.
2. Click **Launch Browser**.
3. You should still be logged in (cookies are persisted).
4. Video plays, stream is detected, download starts.

## Volume Mapping

The `docker-compose.yml` is pre-configured with example paths. You should adjust these to match your host system:

- `./downloads` -> `/app/downloads`: Where finished files are saved.
- `./chrome-data` -> `/app/chrome-data`: Persistence for Chrome user profile (cookies, sessions).
- `./logs` -> `/app/logs`: Application logs.

## Configuration

Environment variables in `docker-compose.yml`:

- `DOWNLOAD_DIR`: Internal path for downloads (Default: `/app/downloads`)
- `CHROME_USER_DATA_DIR`: Internal path for Chrome data (Default: `/app/chrome-data`)
- `AUTO_CLOSE_DELAY`: Seconds to wait before closing browser after detection (Default: 15)
- `DISPLAY`: Xvfb display number (Default: `:99`)

## Troubleshooting

### Browser doesn't open / White screen
- Ensure `shm_size: 2gb` is set in your docker-compose file (Chrome needs shared memory).
- Check logs for "Chrome did not shut down correctly" - use the **Clear Cookies** button in the UI to reset the profile.

### Stream not detected
- Ensure the video is actually playing in the embedded browser.
- Some DRM-protected content (Widevine) cannot be downloaded by FFmpeg.

### Cookies not saving
- Verify the `chrome-data` volume is writable.
- Avoid using "Incognito" or similar features inside the embedded browser (standard session is used by default).

## License

MIT License - See LICENSE file for details.
