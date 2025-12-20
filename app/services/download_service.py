import os
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
        self.download_queue = {}
        self.direct_download_status = {}
        self.download_thumbnails = {}  # Cache for thumbnails

    def start_download(self, browser_id, stream_url, filename, resolution_name, stream_metadata=None):
        """Start a download using FFmpeg"""
        output_path = os.path.join(self.download_dir, filename)

        # Start download in background thread
        threading.Thread(
            target=self._process_download,
            args=(browser_id, stream_url, output_path, resolution_name, stream_metadata),
            daemon=True
        ).start()

        return output_path

    def start_direct_download(self, browser_id, stream_url, filename):
        """Start a direct download with metadata enrichment"""
        output_path = os.path.join(self.download_dir, filename)

        threading.Thread(
            target=self._direct_download,
            args=(browser_id, stream_url, output_path),
            daemon=True
        ).start()

        return browser_id, output_path

    def _thumbnail_updater(self, browser_id, stop_event):
        """Background thread to update thumbnails periodically"""
        logger.debug(f"Starting thumbnail updater for {browser_id}")

        # Check if this is an audio format - skip thumbnails for audio
        if browser_id in self.download_queue:
            file_path = self.download_queue[browser_id].get('output_path')
            if file_path:
                ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                audio_formats = ['mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma']
                if ext in audio_formats:
                    logger.debug(f"Skipping thumbnail generation for audio format: {ext}")
                    return

        while not stop_event.is_set():
            try:
                if browser_id not in self.download_queue:
                    break

                download_info = self.download_queue[browser_id]
                file_path = download_info.get('output_path')
                started_at = download_info.get('started_at', time.time())

                # Calculate dynamic seek time (2 seconds behind live edge)
                elapsed = max(0, time.time() - started_at)
                seek_time = max(0, int(elapsed - 2))

                # Try to extract from file
                thumbnail = None
                if file_path and os.path.exists(file_path):
                    # Force cache timeout to 0 if we are seeking to new position to ensure fresh frame,
                    # effectively bypassing cache for updates, but maybe we want to respect loop interval.
                    # Since we control the loop, we can just pass cache_timeout=1
                    thumbnail = ThumbnailGenerator.extract_thumbnail_from_file(
                        file_path,
                        self.download_thumbnails,
                        browser_id,
                        cache_timeout=1,
                        seek_time=seek_time
                    )

                # Update the download info with the new thumbnail
                if thumbnail:
                    download_info['latest_thumbnail'] = thumbnail
                    # Also update the cache dict so get_active_downloads logic remains consistent if called
                    self.download_thumbnails[browser_id] = {
                        'thumbnail': thumbnail,
                        'timestamp': time.time()
                    }

                # Smart Wait:
                # If we have no thumbnail yet, try eagerly (1s).
                # If we have one, update every 10s.
                wait_time = 10 if download_info.get('latest_thumbnail') else 1
                
            except Exception as e:
                logger.error(f"Error in thumbnail updater for {browser_id}: {e}")
                wait_time = 10 # Fallback
            
            # Wait for calculated time or until stopped
            if stop_event.wait(wait_time):
                break

        logger.debug(f"Stopping thumbnail updater for {browser_id}")

    def _process_download(self, browser_id, stream_url, output_path, resolution_name, stream_metadata=None):
        """Process download in background thread"""
        stop_thumbnail_event = threading.Event()
        thumbnail_thread = None
        
        try:
            logger.info(f"Starting FFmpeg download: {stream_url} -> {output_path}")

            # Get metadata for display
            if stream_metadata:
                resolution_display = stream_metadata.get('resolution') or stream_metadata.get('name', 'Unknown')
                if stream_metadata.get('resolution') and 'x' in str(stream_metadata.get('resolution')):
                    fps = stream_metadata.get('framerate', '').split('.')[0] if stream_metadata.get('framerate') else ''
                    resolution_display = f"{stream_metadata.get('resolution')}@{fps}fps" if fps else stream_metadata.get('resolution')
                elif stream_metadata.get('name'):
                    resolution_display = stream_metadata.get('name')
                metadata = stream_metadata
            else:
                resolution_display = 'Unknown'
                metadata = {}

            # Start FFmpeg process
            process = self._start_ffmpeg_process(stream_url, output_path)

            # Store process info
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
                'latest_thumbnail': None
            }
            
            # Start thumbnail updater
            thumbnail_thread = threading.Thread(
                target=self._thumbnail_updater,
                args=(browser_id, stop_thumbnail_event),
                daemon=True
            )
            thumbnail_thread.start()

            # Wait for completion
            stdout, stderr = process.communicate()

            # Mark as completed
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['completed_at'] = time.time()
                self.download_queue[browser_id]['success'] = (process.returncode == 0)

            if process.returncode == 0:
                logger.info(f"Download completed: {output_path}")
            else:
                logger.error(f"FFmpeg error: {stderr}")

        except Exception as e:
            logger.error(f"Download failed: {e}")
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['completed_at'] = time.time()
                self.download_queue[browser_id]['success'] = False
        finally:
            # Stop thumbnail updater
            if stop_thumbnail_event:
                stop_thumbnail_event.set()

            # Clean up completed download from queue after a short delay
            # This allows get_download_status() to work for scheduler, then removes it
            def cleanup_after_delay():
                time.sleep(30)  # Wait 30 seconds
                if browser_id in self.download_queue and 'completed_at' in self.download_queue[browser_id]:
                    logger.debug(f"Cleaning up completed download from queue: {browser_id}")
                    del self.download_queue[browser_id]
                    # Also clean up thumbnail cache
                    if browser_id in self.download_thumbnails:
                        del self.download_thumbnails[browser_id]

            threading.Thread(target=cleanup_after_delay, daemon=True).start()

    def _direct_download(self, browser_id, stream_url, output_path):
        """Execute direct download with metadata enrichment"""
        stop_thumbnail_event = threading.Event()
        
        try:
            logger.info(f"Starting direct download: {stream_url[:100]}...")

            # Create stream entry for metadata enrichment
            stream_entry = {
                'url': stream_url,
                'bandwidth': 0,
                'resolution': '',
                'framerate': '',
                'codecs': '',
                'name': 'direct'
            }

            # Enrich metadata
            logger.debug("Enriching stream metadata for direct download...")
            MetadataExtractor.enrich_stream_metadata(stream_entry)

            # Generate thumbnail
            logger.debug("Generating thumbnail for direct download...")
            thumbnail = ThumbnailGenerator.generate_stream_thumbnail(stream_url)
            
            # Clean thumbnail for storage
            thumbnail_data = None
            if thumbnail and thumbnail.startswith('data:image/'):
                 thumbnail_data = thumbnail.split(',', 1)[1]
            elif thumbnail:
                 thumbnail_data = thumbnail

            # Prepare metadata
            resolution_display = stream_entry.get('resolution', 'Unknown')
            if stream_entry.get('resolution') and 'x' in str(stream_entry.get('resolution')):
                fps = stream_entry.get('framerate', '').split('.')[0] if stream_entry.get('framerate') else ''
                resolution_display = f"{stream_entry.get('resolution')}@{fps}fps" if fps else stream_entry.get('resolution')

            # Store status
            self.direct_download_status[browser_id] = {
                'browser_id': browser_id,
                'is_running': True,
                'download_started': True,
                'thumbnail': thumbnail_data,
                'selected_stream_metadata': stream_entry
            }

            # Start FFmpeg
            process = self._start_ffmpeg_process(stream_url, output_path)

            # Store in queue
            self.download_queue[browser_id] = {
                'process': process,
                'output_path': output_path,
                'stream_url': stream_url,
                'started_at': time.time(),
                'resolution_name': resolution_display,
                'resolution': stream_entry.get('resolution', 'Unknown'),
                'framerate': stream_entry.get('framerate', 'Unknown'),
                'codecs': stream_entry.get('codecs', 'Unknown'),
                'filename': os.path.basename(output_path),
                'latest_thumbnail': thumbnail_data
            }
            
            # Start thumbnail updater
            threading.Thread(
                target=self._thumbnail_updater,
                args=(browser_id, stop_thumbnail_event),
                daemon=True
            ).start()

            stdout, stderr = process.communicate()

            # Mark as completed
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['completed_at'] = time.time()
                self.download_queue[browser_id]['success'] = (process.returncode == 0)

            if process.returncode == 0:
                logger.info(f"Direct download completed: {output_path}")
            else:
                logger.error(f"Direct download failed: {stderr}")

            # Clean up status
            if browser_id in self.direct_download_status:
                del self.direct_download_status[browser_id]

        except Exception as e:
            logger.error(f"Direct download error: {e}")
            if browser_id in self.download_queue:
                self.download_queue[browser_id]['completed_at'] = time.time()
                self.download_queue[browser_id]['success'] = False
        finally:
            stop_thumbnail_event.set()

            # Clean up completed download from queue after a short delay
            # This allows get_download_status() to work for scheduler, then removes it
            def cleanup_after_delay():
                time.sleep(30)  # Wait 30 seconds
                if browser_id in self.download_queue and 'completed_at' in self.download_queue[browser_id]:
                    logger.debug(f"Cleaning up completed download from queue: {browser_id}")
                    del self.download_queue[browser_id]
                    # Also clean up thumbnail cache
                    if browser_id in self.download_thumbnails:
                        del self.download_thumbnails[browser_id]

            threading.Thread(target=cleanup_after_delay, daemon=True).start()

    def _start_ffmpeg_process(self, stream_url, output_path):
        """Start FFmpeg process for downloading"""
        # Determine output format from extension
        ext = os.path.splitext(output_path)[1].lower().lstrip('.')

        # Audio-only formats
        audio_formats = ['mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma']

        if ext in audio_formats:
            # Audio extraction - need to encode
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',  # Only show errors
                '-i', stream_url,
                '-vn',  # No video
            ]
            
            # Format-specific encoding options
            if ext == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame', '-q:a', '2'])
            elif ext == 'aac':
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            elif ext == 'm4a':
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
            elif ext == 'flac':
                cmd.extend(['-c:a', 'flac'])
            elif ext == 'wav':
                cmd.extend(['-c:a', 'pcm_s16le'])
            elif ext == 'ogg':
                cmd.extend(['-c:a', 'libvorbis', '-q:a', '6'])
            elif ext == 'opus':
                cmd.extend(['-c:a', 'libopus', '-b:a', '128k'])
            elif ext == 'wma':
                cmd.extend(['-c:a', 'wmav2', '-b:a', '192k'])
            
            cmd.extend(['-y', output_path])
        else:
            # Video formats - try stream copy first
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',  # Only show errors
                '-i', stream_url,
            ]
            
            # Format-specific options
            if ext in ['mp4', 'm4v', 'mov']:
                cmd.extend([
                    '-c', 'copy',
                    '-bsf:a', 'aac_adtstoasc',
                    '-movflags', '+frag_keyframe+empty_moov',
                ])
            elif ext == 'mkv':
                cmd.extend(['-c', 'copy'])
            elif ext == 'webm':
                # WebM may need re-encoding if source isn't VP8/VP9
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
                # Default: stream copy
                cmd.extend(['-c', 'copy'])
            
            cmd.extend(['-y', output_path])

        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

    def get_active_downloads(self):
        """Get list of active downloads with progress"""
        active = []

        for browser_id, download_info in list(self.download_queue.items()):
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

    def stop_download(self, browser_id):
        """Stop an active download"""
        if browser_id in self.download_queue:
            download_info = self.download_queue[browser_id]
            process = download_info.get('process')

            if process and process.poll() is None:
                logger.debug(f"Stopping download for browser {browser_id}")
                process.terminate()
                process.wait(timeout=5)
                logger.debug(f"Download stopped for browser {browser_id}")

            del self.download_queue[browser_id]
            return True
        return False

    def get_download_status(self, browser_id):
        """Get download status for a specific browser_id"""
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
