# MARS
## Media Archive Recording System

> [!CAUTION]
> **LEGAL DISCLAIMER**: This software is intended for personal use only. Users must only download content they have the legal right to access and store (e.g., public domain content, content under free licenses, or content for which they have explicit permission). The developers of this software are not responsible for any misuse, copyright infringement, or violations of Terms of Service. Do not use this tool for commercial purposes or to distribute copyrighted material without permission.

A self-hosted media archiving system designed for Docker environments. Record and archive streams with intelligent scheduling, browser-based authentication, and automated retry capabilities.

## Features

### Download Modes

- **Direct Download**: Download directly from URLs (.m3u8, .mpd, .mp4) with support for format conversion.
- **Browser Mode**: Interactive Chrome browser to navigate, log in, and automatically detect video streams.
- **Scheduled Downloads**: Automated stream recording with intelligent retry and resilience features.

### Format Support

- **Video**: MP4, MKV, WebM, MOV, AVI, FLV, WMV, TS
- **Audio Extraction**: MP3, AAC, M4A, FLAC, WAV, OGG, OPUS, WMA
- **Quality Options**: Source (highest), 4K (2160p), 1440p, 1080p, 720p, 480p, 360p, 160p
- **Frame Rate**: Any, 60 FPS, 30 FPS

### Advanced Browser Capabilities

- **Cookie Persistence**: Log in once, stay logged in for sites requiring authentication
- **Stream Detection**: Automatically detects HLS, DASH, and progressive streams
- **Manual Control**: Select specific resolutions or streams when multiple are detected
- **Clear Cookies**: Built-in tool to clear browser data if needed
- **noVNC Integration**: View and interact with the browser directly within the web interface

### Intelligent Scheduling

- **Time Windows**: Schedule downloads for specific time ranges (e.g., 14:00-16:00)
- **Daily Repeats**: Automatically repeat schedules every day at the same time
- **Weekly Repeats**: Schedule recurring downloads for specific days
- **Auto-Resume**: If a stream crashes or disconnects, automatically resume checking within the time window
- **Manual Stop Control**: User-stopped downloads won't auto-resume (respects your decision)
- **Multiple Streams**: Handle multiple concurrent streams from the same schedule
- **Custom Naming**: Optional name prefix for organized file naming

### File Management

- **Smart Naming**: Automatic timestamped filenames in format `HH-MM-SS-DDD-MMM` (e.g., `14-30-45-Mon-Jan.mp4`)
- **Custom Prefixes**: Add optional names to scheduled downloads (e.g., `MyStream-14-30-45-Mon-Jan.mp4`)
- **Thumbnail Generation**: Visual confirmation of downloaded content
- **Background Processing**: Downloads run in the background with real-time progress tracking
- **Metadata Extraction**: Duration, resolution, and codec information

### System

- **Dockerized**: Optimized for containerized deployment
- **Hardware Acceleration**: Potential support for GPU acceleration
- **Persistent Storage**: Chrome data, downloads, and logs are preserved across container restarts
- **Real-time Monitoring**: Live progress updates and download status

## Quick Start

### Using Docker Compose (Recommended)

1. **Download the example compose file:**
   ```bash
   wget https://raw.githubusercontent.com/DorkSoul/MARS/main/docker-compose.example -O docker-compose.yml
   ```

   Or create a `docker-compose.yml` file with this content:
   ```yaml
   version: '3.8'

   services:
     mars:
       image: ghcr.io/dorksoul/mars:latest
       container_name: mars
       restart: unless-stopped
       ports:
         - "5000:5000" # Flask web interface
         - "6080:6080" # noVNC
       volumes:
         - ./downloads:/app/downloads:rw
         - ./chrome-data:/app/chrome-data:rw
         - ./logs:/app/logs:rw
       environment:
         - DISPLAY=:99
         - CHROME_USER_DATA_DIR=/app/chrome-data
         - DOWNLOAD_DIR=/app/downloads
         - AUTO_CLOSE_DELAY=15
         - FLASK_ENV=production
       shm_size: 2gb
       security_opt:
         - seccomp:unconfined
   ```

2. **Adjust volume paths** in the compose file to match your system (if needed)

3. **Deploy the container:**
   ```bash
   docker-compose up -d
   ```

4. **Check logs:**
   ```bash
   docker-compose logs -f
   ```

5. **Update to the latest version:**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

## Access

- **Web Interface**: `http://your-server-ip:5000`
- **Internal VNC**: Accessed via the "View Browser" button in the web interface (port 6080 internally)

## Usage

### Direct Download Mode

1. Open the web interface
2. Select **Direct Download** tab
3. Paste a stream URL (e.g., `.m3u8` or `.mp4`)
4. (Optional) Enter a custom filename
5. Select the **Output Format** (Video or Audio)
6. Click **Download**

### Browser Mode (Find Link)

**First time on a new site:**

1. Select **Browser Mode** tab
2. Enter the webpage URL (e.g., `https://videosite.com/watch/12345`)
3. Select desired **Resolution**, **Frame Rate**, and **Output Format**
4. Click **Launch Browser**
5. The browser view will appear. **Log in** to the site if necessary
6. Navigate to the video and play it
7. The system will detect the stream and offer to download it
8. Confirm the download (or it will auto-start if configured)

**Next time on the same site:**

1. Paste a new video URL
2. Click **Launch Browser**
3. You should still be logged in (cookies are persisted)
4. Video plays, stream is detected, download starts

### Scheduled Downloads

**Create a Schedule:**

1. Select **Schedules** tab
2. Enter the **Webpage URL** where the stream will be available
3. (Optional) Enter a **Name** to prefix filenames (e.g., `MyStream`)
4. Check **Run Daily** for daily repeats, or use date/time pickers for specific times
5. Set **Start Time** and **End Time** for the recording window
6. Select **Resolution**, **Frame Rate**, and **Output Format**
7. (Optional) Check **Repeat Weekly** for weekly recurring schedules
8. Click **Add Schedule**

**How Schedules Work:**

- **Automatic Checking**: Browser opens automatically during the time window to check for streams
- **Stream Detection**: If a stream is found, recording starts immediately
- **Auto-Resume**: If the stream crashes or disconnects, the scheduler automatically resumes checking
- **Manual Control**: If you click "Stop" on a download, it won't auto-resume until the next time window
- **Smart Naming**: Files are automatically named with timestamps and your optional prefix
- **Multiple Attempts**: Can handle multiple stream starts/stops within one time window

**Example Schedule:**

- **URL**: `https://twitch.tv/streamer`
- **Name**: `MyFavoriteStreamer`
- **Time**: 14:00 - 16:00 (Daily)
- **Resolution**: 1080p
- **Format**: MP4

Result: Every day from 14:00-16:00, the system checks for streams and saves them as `MyFavoriteStreamer-HH-MM-SS-DDD-MMM.mp4`

## File Naming

### Auto-Generated Names

Files are automatically named using the format: `HH-MM-SS-DDD-MMM.ext`

- **HH**: Hour (00-23)
- **MM**: Minute (00-59)
- **SS**: Second (00-59)
- **DDD**: Day abbreviation (Mon, Tue, Wed, etc.)
- **MMM**: Month abbreviation (Jan, Feb, Mar, etc.)

Example: `14-30-45-Mon-Jan.mp4` (started at 2:30:45 PM on a Monday in January)

### Custom Prefixes

For scheduled downloads, add an optional name to prefix the timestamp:

- **With name**: `MyStream-14-30-45-Mon-Jan.mp4`
- **Without name**: `14-30-45-Mon-Jan.mp4`

## Volume Mapping

The `docker-compose.example` file provides default paths that work for most users. Adjust these to match your host system:

- `./downloads` -> `/app/downloads`: Where finished files are saved
- `./chrome-data` -> `/app/chrome-data`: Persistence for Chrome user profile (cookies, sessions)
- `./logs` -> `/app/logs`: Application logs

**Example custom paths:**
```yaml
volumes:
  - /path/to/your/media:/app/downloads:rw
  - /path/to/persistent/chrome:/app/chrome-data:rw
  - /path/to/logs:/app/logs:rw
```

## Building from Source (Optional)

If you want to build the Docker image yourself instead of using the pre-built image:

```bash
# Clone the repository
git clone https://github.com/DorkSoul/MARS.git
cd MARS

# Build the image
docker build -t mars:latest .

# Update docker-compose.yml to use your local image
# Change: image: ghcr.io/dorksoul/mars:latest
# To:     image: mars:latest

# Deploy
docker-compose up -d
```

## Configuration

Environment variables in `docker-compose.yml`:

- `DOWNLOAD_DIR`: Internal path for downloads (Default: `/app/downloads`)
- `CHROME_USER_DATA_DIR`: Internal path for Chrome data (Default: `/app/chrome-data`)
- `AUTO_CLOSE_DELAY`: Seconds to wait before closing browser after detection (Default: 15)
- `DISPLAY`: Xvfb display number (Default: `:99`)

## Troubleshooting

### Browser doesn't open / White screen

- Ensure `shm_size: 2gb` is set in your docker-compose file (Chrome needs shared memory)
- Check logs for "Chrome did not shut down correctly" - use the **Clear Cookies** button in the UI to reset the profile

### Stream not detected

- Ensure the video is actually playing in the embedded browser
- Some DRM-protected content (Widevine) cannot be downloaded by FFmpeg
- Wait a few seconds for the detection to occur (streams are detected via network monitoring)

### Cookies not saving

- Verify the `chrome-data` volume is writable
- Avoid using "Incognito" or similar features inside the embedded browser

### Schedule not triggering

- Check the schedule status in the web interface
- Verify the time window is correct (times are in the server's timezone)
- Check logs for error messages
- Ensure the browser can reach the URL

### Download keeps restarting after I stopped it

- This is expected behavior for automatic failures (stream crashes)
- If you manually click "Stop", the schedule will respect your decision and wait for the next time window
- To permanently disable a schedule, delete it from the Schedules tab

### Multiple downloads from same schedule

- The system tracks specific downloads by unique IDs
- If download A fails and download B is still running, the system correctly handles both
- Only the most recent download attempt is monitored for auto-resume

## Advanced Features

### Schedule Resilience

The intelligent scheduling system provides robust stream recording:

1. **Auto-Resume on Failure**: If a stream crashes, internet disconnects, or the streamer restarts, the system automatically resumes checking within the time window
2. **Manual Stop Respect**: User-stopped downloads won't auto-resume (respects your control)
3. **Multiple Concurrent Streams**: Can handle multiple simultaneous streams from the same schedule
4. **Specific Download Tracking**: Tracks individual download attempts to avoid conflicts

### Download Monitoring

- **Real-time Progress**: See download progress, duration, and status
- **Live Thumbnails**: Preview what's being recorded (updates every 10 seconds)
- **File Size Tracking**: Monitor download size as it grows
- **Stop/Resume Control**: Full control over active downloads

## License

MIT License - See LICENSE file for details.
