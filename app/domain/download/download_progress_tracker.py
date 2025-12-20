import os
import time
import logging
import threading
from app.utils import ThumbnailGenerator

logger = logging.getLogger(__name__)


class DownloadProgressTracker:
    """Tracks download progress, status, and thumbnails"""

    def __init__(self):
        self.download_queue = {}
        self.direct_download_status = {}
        self.download_thumbnails = {}
        self._lock = threading.Lock()

    def add_download(self, browser_id, process, output_path, stream_url, resolution_display, metadata, thumbnail=None):
        """Add a new download to tracking"""
        with self._lock:
            self.download_queue[browser_id] = {
                'process': process,
                'output_path': output_path,
                'stream_url': stream_url,
                'started_at': time.time(),
                'resolution_name': resolution_display,
                'resolution': metadata.get('resolution', 'Unknown'),
                'framerate': metadata.get('framerate', 'Unknown'),
                'codecs': metadata.get('codecs', 'Unknown'),
                'filename': os.path.basename(output_path),
                'latest_thumbnail': thumbnail
            }

    def update_thumbnail(self, browser_id, thumbnail):
        """Update the thumbnail for a download"""
        with self._lock:
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['latest_thumbnail'] = thumbnail
                self.download_thumbnails[browser_id] = {
                    'thumbnail': thumbnail,
                    'timestamp': time.time()
                }

    def mark_completed(self, browser_id, success=True):
        """Mark a download as completed"""
        with self._lock:
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['completed_at'] = time.time()
                self.download_queue[browser_id]['success'] = success

    def remove_download(self, browser_id):
        """Remove a download from tracking"""
        with self._lock:
            if browser_id in self.download_queue:
                del self.download_queue[browser_id]
            if browser_id in self.download_thumbnails:
                del self.download_thumbnails[browser_id]

    def get_download_info(self, browser_id):
        """Get download info for a specific browser_id (thread-safe read)"""
        with self._lock:
            return self.download_queue.get(browser_id)

    def get_download_status(self, browser_id):
        """Get download status for a specific browser_id"""
        with self._lock:
            if browser_id in self.download_queue:
                download_info = self.download_queue[browser_id]
                # Calculate duration
                if 'completed_at' in download_info:
                    duration = download_info['completed_at'] - download_info['started_at']
                else:
                    duration = time.time() - download_info['started_at']

                return {
                    'output_path': download_info['output_path'],
                    'stream_url': download_info['stream_url'],
                    'duration': duration,
                    'completed': 'completed_at' in download_info,
                    'success': download_info.get('success', True)
                }
            return None

    def get_all_downloads(self):
        """Get list of all downloads with progress"""
        active = []

        with self._lock:
            queue_items = list(self.download_queue.items())

        for browser_id, download_info in queue_items:
            # Skip completed downloads
            if 'completed_at' in download_info:
                continue

            process = download_info.get('process')
            output_path = download_info.get('output_path')
            started_at = download_info.get('started_at')

            # Check file size
            file_size = 0
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)

            # Calculate duration
            duration = int(time.time() - started_at)

            # Check if process is still running
            is_running = process.poll() is None if process else False

            # Use cached thumbnail managed by background thread
            thumbnail = download_info.get('latest_thumbnail')

            active.append({
                'browser_id': browser_id,
                'filename': download_info.get('filename', 'Unknown'),
                'resolution': download_info.get('resolution_name', 'Unknown'),
                'resolution_detail': download_info.get('resolution', 'Unknown'),
                'framerate': download_info.get('framerate', 'Unknown'),
                'codecs': download_info.get('codecs', 'Unknown'),
                'size': file_size,
                'duration': duration,
                'is_running': is_running,
                'thumbnail': thumbnail
            })

        return active

    def has_download(self, browser_id):
        """Check if a download exists"""
        with self._lock:
            return browser_id in self.download_queue

    def is_audio_format(self, browser_id):
        """Check if the download is an audio format"""
        with self._lock:
            if browser_id in self.download_queue:
                file_path = self.download_queue[browser_id].get('output_path')
                if file_path:
                    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                    audio_formats = ['mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma']
                    return ext in audio_formats
            return False

    def add_direct_download_status(self, browser_id, thumbnail, stream_metadata):
        """Add direct download status"""
        # Clean thumbnail for storage
        thumbnail_data = None
        if thumbnail and thumbnail.startswith('data:image/'):
            thumbnail_data = thumbnail.split(',', 1)[1]
        elif thumbnail:
            thumbnail_data = thumbnail

        with self._lock:
            self.direct_download_status[browser_id] = {
                'browser_id': browser_id,
                'is_running': True,
                'download_started': True,
                'thumbnail': thumbnail_data,
                'selected_stream_metadata': stream_metadata
            }

    def remove_direct_download_status(self, browser_id):
        """Remove direct download status"""
        with self._lock:
            if browser_id in self.direct_download_status:
                del self.direct_download_status[browser_id]

    def schedule_cleanup(self, browser_id, delay=30):
        """Schedule cleanup of completed download after delay"""
        def cleanup_after_delay():
            time.sleep(delay)
            with self._lock:
                if browser_id in self.download_queue and 'completed_at' in self.download_queue[browser_id]:
                    logger.debug(f"Cleaning up completed download from queue: {browser_id}")
                    del self.download_queue[browser_id]
                    # Also clean up thumbnail cache
                    if browser_id in self.download_thumbnails:
                        del self.download_thumbnails[browser_id]

        threading.Thread(target=cleanup_after_delay, daemon=True).start()

    def update_thumbnail_from_file(self, browser_id):
        """Update thumbnail by extracting from the download file"""
        download_info = self.get_download_info(browser_id)
        if not download_info:
            return None

        file_path = download_info.get('output_path')
        started_at = download_info.get('started_at', time.time())

        # Calculate dynamic seek time (2 seconds behind live edge)
        elapsed = max(0, time.time() - started_at)
        seek_time = max(0, int(elapsed - 2))

        # Try to extract from file
        thumbnail = None
        if file_path and os.path.exists(file_path):
            thumbnail = ThumbnailGenerator.extract_thumbnail_from_file(
                file_path,
                self.download_thumbnails,
                browser_id,
                cache_timeout=1,
                seek_time=seek_time
            )

        # Update the download info with the new thumbnail
        if thumbnail:
            self.update_thumbnail(browser_id, thumbnail)

        return thumbnail
