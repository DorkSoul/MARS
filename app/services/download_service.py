import os
import json
import time
import logging
import subprocess
import threading
from app.utils import MetadataExtractor, ThumbnailGenerator

logger = logging.getLogger(__name__)


class DownloadService:
    """Manages video downloads using FFmpeg"""

    def __init__(self, download_dir):
        self.download_dir = download_dir
        self._queue_lock = threading.Lock()
        self.download_queue = {}          # protected by _queue_lock
        self.direct_download_status = {}  # protected by _queue_lock
        self.download_thumbnails = {}     # protected by _queue_lock
        self._history_file = os.path.join(download_dir, '.download_history.json')

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start_download(self, browser_id, stream_url, filename, resolution_name, stream_metadata=None):
        """Start a stream download using FFmpeg (called by browser/stream detector)."""
        output_path = os.path.join(self.download_dir, filename)
        threading.Thread(
            target=self._process_download,
            args=(browser_id, stream_url, output_path, resolution_name, stream_metadata),
            daemon=True
        ).start()
        return output_path

    def start_direct_download(self, browser_id, stream_url, filename):
        """Start a direct URL download with metadata enrichment."""
        output_path = os.path.join(self.download_dir, filename)
        threading.Thread(
            target=self._direct_download,
            args=(browser_id, stream_url, output_path),
            daemon=True
        ).start()
        return browser_id, output_path

    def stop_download(self, browser_id):
        """Stop an active download, escalating from SIGTERM to SIGKILL if needed."""
        with self._queue_lock:
            if browser_id not in self.download_queue:
                return False
            download_info = self.download_queue.pop(browser_id)
            self.download_thumbnails.pop(browser_id, None)

        process = download_info.get('process')
        if process and process.poll() is None:
            logger.debug(f"Terminating download {browser_id}")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"SIGTERM timed out for {browser_id}, escalating to SIGKILL")
                process.kill()
                process.wait()

        return True

    def get_active_downloads(self):
        """Get list of active downloads with progress."""
        with self._queue_lock:
            items = list(self.download_queue.items())

        active = []
        for browser_id, download_info in items:
            if 'completed_at' in download_info:
                continue

            process = download_info.get('process')
            output_path = download_info.get('output_path')
            started_at = download_info.get('started_at', time.time())

            file_size = 0
            if output_path and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)

            active.append({
                'browser_id': browser_id,
                'filename': download_info.get('filename', 'Unknown'),
                'resolution': download_info.get('resolution_name', 'Unknown'),
                'resolution_detail': download_info.get('resolution', 'Unknown'),
                'framerate': download_info.get('framerate', 'Unknown'),
                'codecs': download_info.get('codecs', 'Unknown'),
                'size': file_size,
                'duration': int(time.time() - started_at),
                'is_running': process.poll() is None if process else False,
                'thumbnail': download_info.get('latest_thumbnail'),
            })

        return active

    def get_download_status(self, browser_id):
        """Get download status for a specific browser_id."""
        with self._queue_lock:
            download_info = self.download_queue.get(browser_id)

        if download_info is None:
            return None

        if 'completed_at' in download_info:
            duration = download_info['completed_at'] - download_info['started_at']
        else:
            duration = time.time() - download_info['started_at']

        return {
            'output_path': download_info['output_path'],
            'stream_url': download_info['stream_url'],
            'duration': duration,
            'completed': 'completed_at' in download_info,
            'success': download_info.get('success', True),
        }

    def get_history(self):
        """Return the persisted download history list."""
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading download history: {e}")
        return []

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _process_download(self, browser_id, stream_url, output_path, resolution_name, stream_metadata=None):
        """Thin wrapper: compute display name then delegate to shared core."""
        if stream_metadata:
            resolution_display = stream_metadata.get('resolution') or stream_metadata.get('name', 'Unknown')
            if stream_metadata.get('resolution') and 'x' in str(stream_metadata.get('resolution')):
                fps = stream_metadata.get('framerate', '').split('.')[0] if stream_metadata.get('framerate') else ''
                resolution_display = (
                    f"{stream_metadata['resolution']}@{fps}fps" if fps else stream_metadata['resolution']
                )
            elif stream_metadata.get('name'):
                resolution_display = stream_metadata['name']
        else:
            resolution_display = resolution_name or 'Unknown'
            stream_metadata = {}

        self._run_download_core(browser_id, stream_url, output_path, resolution_display, stream_metadata)

    def _direct_download(self, browser_id, stream_url, output_path):
        """Enrich metadata, generate thumbnail, then run shared core download."""
        try:
            logger.info(f"Starting direct download: {stream_url[:100]}...")

            stream_entry = {
                'url': stream_url,
                'bandwidth': 0,
                'resolution': '',
                'framerate': '',
                'codecs': '',
                'name': 'direct',
            }
            MetadataExtractor.enrich_stream_metadata(stream_entry)

            thumbnail = ThumbnailGenerator.generate_stream_thumbnail(stream_url)
            thumbnail_data = None
            if thumbnail and thumbnail.startswith('data:image/'):
                thumbnail_data = thumbnail.split(',', 1)[1]
            elif thumbnail:
                thumbnail_data = thumbnail

            resolution_display = stream_entry.get('resolution', 'Unknown')
            if stream_entry.get('resolution') and 'x' in str(stream_entry.get('resolution')):
                fps = stream_entry.get('framerate', '').split('.')[0] if stream_entry.get('framerate') else ''
                resolution_display = (
                    f"{stream_entry['resolution']}@{fps}fps" if fps else stream_entry['resolution']
                )

            with self._queue_lock:
                self.direct_download_status[browser_id] = {
                    'browser_id': browser_id,
                    'is_running': True,
                    'download_started': True,
                    'thumbnail': thumbnail_data,
                    'selected_stream_metadata': stream_entry,
                }

            self._run_download_core(
                browser_id, stream_url, output_path,
                resolution_display, stream_entry,
                initial_thumbnail=thumbnail_data,
            )

        except Exception as e:
            logger.error(f"Direct download error: {e}")
            with self._queue_lock:
                if browser_id in self.download_queue:
                    self.download_queue[browser_id]['completed_at'] = time.time()
                    self.download_queue[browser_id]['success'] = False
        finally:
            with self._queue_lock:
                self.direct_download_status.pop(browser_id, None)

    def _run_download_core(self, browser_id, stream_url, output_path, resolution_display, metadata, initial_thumbnail=None):
        """Core download execution: FFmpeg subprocess, thumbnail updates, history write."""
        stop_thumbnail_event = threading.Event()
        started_at = time.time()

        try:
            logger.info(f"Starting FFmpeg download: {stream_url} -> {output_path}")
            process = self._start_ffmpeg_process(stream_url, output_path)

            queue_entry = {
                'process': process,
                'output_path': output_path,
                'stream_url': stream_url,
                'started_at': started_at,
                'resolution_name': resolution_display,
                'resolution': metadata.get('resolution', 'Unknown'),
                'framerate': metadata.get('framerate', 'Unknown'),
                'codecs': metadata.get('codecs', 'Unknown'),
                'filename': os.path.basename(output_path),
                'latest_thumbnail': initial_thumbnail,
            }
            with self._queue_lock:
                self.download_queue[browser_id] = queue_entry

            thumbnail_thread = threading.Thread(
                target=self._thumbnail_updater,
                args=(browser_id, stop_thumbnail_event),
                daemon=True,
            )
            thumbnail_thread.start()

            stdout, stderr = process.communicate()

            success = process.returncode == 0
            completed_at = time.time()

            with self._queue_lock:
                if browser_id in self.download_queue:
                    self.download_queue[browser_id]['completed_at'] = completed_at
                    self.download_queue[browser_id]['success'] = success

            if success:
                logger.info(f"Download completed: {output_path}")
            else:
                logger.error(f"FFmpeg error (rc={process.returncode}): {stderr}")

            self._append_history({
                'browser_id': browser_id,
                'filename': os.path.basename(output_path),
                'stream_url': stream_url,
                'resolution': metadata.get('resolution', 'Unknown'),
                'framerate': metadata.get('framerate', 'Unknown'),
                'started_at': started_at,
                'completed_at': completed_at,
                'duration_s': round(completed_at - started_at, 1),
                'success': success,
                'file_size': os.path.getsize(output_path) if os.path.exists(output_path) else 0,
            })

        except Exception as e:
            logger.error(f"Download failed: {e}")
            with self._queue_lock:
                if browser_id in self.download_queue:
                    self.download_queue[browser_id]['completed_at'] = time.time()
                    self.download_queue[browser_id]['success'] = False
        finally:
            stop_thumbnail_event.set()
            # Use a Timer instead of spawning a thread just to sleep
            threading.Timer(30.0, self._cleanup_download, args=(browser_id,)).start()

    def _cleanup_download(self, browser_id):
        """Remove a completed download entry from the queue (called by Timer after 30 s)."""
        with self._queue_lock:
            info = self.download_queue.get(browser_id)
            if info and 'completed_at' in info:
                logger.debug(f"Cleaning up completed download from queue: {browser_id}")
                del self.download_queue[browser_id]
                self.download_thumbnails.pop(browser_id, None)

    def _thumbnail_updater(self, browser_id, stop_event):
        """Background thread to periodically extract and cache a live thumbnail."""
        logger.debug(f"Starting thumbnail updater for {browser_id}")

        # Skip audio-only formats up front
        with self._queue_lock:
            file_path = self.download_queue.get(browser_id, {}).get('output_path', '')
        if file_path:
            ext = os.path.splitext(file_path)[1].lower().lstrip('.')
            if ext in {'mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma'}:
                logger.debug(f"Skipping thumbnail generation for audio format: {ext}")
                return

        while not stop_event.is_set():
            try:
                with self._queue_lock:
                    if browser_id not in self.download_queue:
                        break
                    info = self.download_queue[browser_id]
                    file_path = info.get('output_path')
                    started_at = info.get('started_at', time.time())
                    has_thumbnail = bool(info.get('latest_thumbnail'))

                elapsed = max(0, time.time() - started_at)
                seek_time = max(0, int(elapsed - 2))

                thumbnail = None
                if file_path and os.path.exists(file_path):
                    thumbnail = ThumbnailGenerator.extract_thumbnail_from_file(
                        file_path,
                        self.download_thumbnails,
                        browser_id,
                        cache_timeout=1,
                        seek_time=seek_time,
                    )

                if thumbnail:
                    with self._queue_lock:
                        if browser_id in self.download_queue:
                            self.download_queue[browser_id]['latest_thumbnail'] = thumbnail
                    self.download_thumbnails[browser_id] = {
                        'thumbnail': thumbnail,
                        'timestamp': time.time(),
                    }
                    has_thumbnail = True

                wait_time = 10 if has_thumbnail else 1

            except Exception as e:
                logger.error(f"Error in thumbnail updater for {browser_id}: {e}")
                wait_time = 10

            if stop_event.wait(wait_time):
                break

        logger.debug(f"Stopping thumbnail updater for {browser_id}")

    def _append_history(self, entry):
        """Append a completed download record to the persistent history file."""
        try:
            history = []
            if os.path.exists(self._history_file):
                try:
                    with open(self._history_file, 'r') as f:
                        history = json.load(f)
                except Exception:
                    history = []
            history.append(entry)
            with open(self._history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing download history: {e}")

    def _start_ffmpeg_process(self, stream_url, output_path):
        """Build and launch the appropriate FFmpeg command for the given output format."""
        ext = os.path.splitext(output_path)[1].lower().lstrip('.')
        audio_formats = {'mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma'}

        if ext in audio_formats:
            cmd = ['ffmpeg', '-loglevel', 'error', '-i', stream_url, '-vn']
            codec_map = {
                'mp3':  ['-c:a', 'libmp3lame', '-q:a', '2'],
                'aac':  ['-c:a', 'aac', '-b:a', '192k'],
                'm4a':  ['-c:a', 'aac', '-b:a', '192k'],
                'flac': ['-c:a', 'flac'],
                'wav':  ['-c:a', 'pcm_s16le'],
                'ogg':  ['-c:a', 'libvorbis', '-q:a', '6'],
                'opus': ['-c:a', 'libopus', '-b:a', '128k'],
                'wma':  ['-c:a', 'wmav2', '-b:a', '192k'],
            }
            cmd.extend(codec_map.get(ext, ['-c:a', 'copy']))
        else:
            cmd = ['ffmpeg', '-loglevel', 'error', '-i', stream_url]
            if ext in ('mp4', 'm4v', 'mov'):
                cmd.extend(['-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                             '-movflags', '+frag_keyframe+empty_moov'])
            elif ext == 'mkv':
                cmd.extend(['-c', 'copy'])
            elif ext == 'webm':
                cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])
            elif ext == 'ts':
                cmd.extend(['-c', 'copy', '-bsf:v', 'h264_mp4toannexb'])
            elif ext == 'flv':
                cmd.extend(['-c', 'copy'])
            elif ext == 'wmv':
                cmd.extend(['-c:v', 'wmv2', '-c:a', 'wmav2'])
            elif ext == 'avi':
                cmd.extend(['-c', 'copy'])
            else:
                cmd.extend(['-c', 'copy'])

        cmd.extend(['-y', output_path])

        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
