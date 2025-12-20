"""
Download management
Mixin for StreamDetector class
"""
import logging
import json
import time
import threading
import websocket
import requests as req_lib

from app.utils import MetadataExtractor, ThumbnailGenerator

logger = logging.getLogger(__name__)


class DownloadHandlerMixin:
    """Download management"""
    def _enrich_and_add_thumbnail(self, stream_dict):
        """Enrich stream metadata and add thumbnail"""
        try:
            # Enrich metadata
            MetadataExtractor.enrich_stream_metadata(stream_dict)

            # Add thumbnail
            stream_url = stream_dict.get('url')
            if stream_url:
                thumbnail = ThumbnailGenerator.generate_stream_thumbnail(stream_url)
                if thumbnail:
                    stream_dict['thumbnail'] = thumbnail
        except Exception:
            pass

    def _start_download_with_stream(self, stream):
        """Start download with stream object"""
        resolution_name = stream.get('name', 'video')
        self._start_download_with_url(stream['url'], resolution_name, stream)

    def _start_download_with_url(self, stream_url, resolution_name, stream_metadata=None):
        """Start download with specific URL"""
        self.download_started = True
        self.selected_stream_url = stream_url
        self.selected_stream_metadata = stream_metadata

        logger.info(f"Starting download for resolution: {resolution_name}")

        # Reuse thumbnail if available
        if stream_metadata and 'thumbnail' in stream_metadata:
            thumbnail = stream_metadata['thumbnail']
            if thumbnail.startswith('data:image/'):
                self.thumbnail_data = thumbnail.split(',', 1)[1]
            else:
                self.thumbnail_data = thumbnail

        # Generate filename
        ext = self.output_format
        if self.filename:
            # Check if filename already has an extension
            if '.' in self.filename:
                filename = self.filename
            else:
                filename = f"{self.filename}.{ext}"
        else:
            timestamp = int(time.time())
            filename = f"video_{resolution_name}_{timestamp}.{ext}"

        # Call download callback if set
        if self.download_callback:
            self.download_callback(self.browser_id, stream_url, filename, resolution_name, stream_metadata)

        # Wait for video to load
        time.sleep(3)

        # Capture thumbnail if not available
        if not self.thumbnail_data:
            self.thumbnail_data = ThumbnailGenerator.capture_screenshot(self.driver)

