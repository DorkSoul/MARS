"""
Stream parsing and detection
Mixin for StreamDetector class
"""
import logging
import json
import time
import threading
import websocket
import requests as req_lib

from app.utils import PlaylistParser

logger = logging.getLogger(__name__)


class StreamParserMixin:
    """Stream parsing and detection"""
    def _is_video_stream(self, url, mime_type):
        """Check if URL is a video stream - ONLY playlists, not segments"""
        # ONLY accept playlist files (.m3u8, .mpd), NOT individual segments (.ts, .m4s)
        playlist_extensions = ['.m3u8', '.mpd']
        playlist_mime_types = ['application/vnd.apple.mpegurl', 'application/dash+xml',
                               'application/x-mpegurl', 'vnd.apple.mpegurl']

        # Filter out individual segment files
        if url.lower().endswith('.ts') or url.lower().endswith('.m4s') or '/segment/' in url.lower():
            return False

        # HIGH PRIORITY: Twitch HLS API endpoint
        if 'usher.ttvnw.net' in url.lower() and '.m3u8' in url.lower():
            return True

        # Check for playlist extensions
        if any(url.lower().endswith(ext) or f'{ext}?' in url.lower() for ext in playlist_extensions):
            # Filter out ads and tracking
            if any(keyword in url.lower() for keyword in ['doubleclick', 'analytics', 'tracking']):
                return False
            return True

        # Check for playlist in path
        if 'playlist' in url.lower() and '.m3u8' in url.lower():
            return True

        # Check MIME type for playlists
        if any(mime in mime_type.lower() for mime in playlist_mime_types):
            return True

        return False

    def _is_likely_master_playlist(self, url):
        """Check if URL is likely a master playlist"""
        return (
            'usher' in url.lower() or
            'master' in url.lower() or
            '/playlist.m3u8' in url.lower() or
            '/index.m3u8' in url.lower() or
            'api' in url.lower()
        )

    def _is_likely_media_playlist(self, url):
        """Check if URL is likely a media playlist (not master)"""
        return (
            '/chunklist' in url.lower() or
            '/media_' in url.lower() or
            '/segment' in url.lower()
        )

    def _get_stream_type(self, url):
        """Determine stream type from URL"""
        if '.m3u8' in url.lower():
            return 'HLS'
        elif '.mpd' in url.lower():
            return 'DASH'
        elif '.mp4' in url.lower():
            return 'MP4'
        else:
            return 'UNKNOWN'

    def _add_detected_stream(self, url, mime_type, stream_type=None):
        """Add a detected stream and trigger processing"""
        if stream_type is None:
            stream_type = self._get_stream_type(url)

        stream_info = {
            'url': url,
            'type': stream_type,
            'mime_type': mime_type,
            'timestamp': time.time()
        }

        if stream_info not in self.detected_streams:
            logger.info(f"✓ DETECTED STREAM: type={stream_info['type']}")
            self.detected_streams.append(stream_info)

            # Start download for the first valid stream
            if not self.download_started and not self.awaiting_resolution_selection:
                logger.info(f"Processing detected stream...")
                self._handle_stream_detection(stream_info)

    def _handle_stream_detection(self, stream_info):
        """Handle detected stream - check if it's a master playlist"""
        stream_url = stream_info['url']

        if '.m3u8' in stream_url.lower():
            content = PlaylistParser.fetch_master_playlist(stream_url)

            if content and '#EXT-X-STREAM-INF:' in content:
                self._process_master_playlist(stream_url, content)
            else:
                self._process_single_stream(stream_url, stream_info)
        else:
            self._process_single_stream(stream_url, stream_info)

    def _process_master_playlist(self, stream_url, content):
        """Process a master playlist with multiple resolutions"""
        resolutions = PlaylistParser.parse_master_playlist(content)

        if resolutions:
            if self.auto_download:
                matched_stream = self._match_stream(resolutions)

                if matched_stream:
                    logger.info(f"Matched stream: {matched_stream['name']}")
                    self._enrich_and_add_thumbnail(matched_stream)
                    self._start_download_with_stream(matched_stream)
                else:
                    self._show_stream_selection(resolutions)
            else:
                self._show_stream_selection(resolutions)
        else:
            self._show_unparsed_stream(stream_url)

    def _process_single_stream(self, stream_url, stream_info):
        """Process a single stream (not a master playlist)"""
        stream_entry = {
            'url': stream_url,
            'bandwidth': 0,
            'resolution': '',
            'framerate': '',
            'codecs': '',
            'name': stream_info['type']
        }

        if self.auto_download:
            self._enrich_and_add_thumbnail(stream_entry)
            self._start_download_with_url(stream_url, stream_info['type'], stream_entry)
        else:
            self._show_stream_selection([stream_entry])

    def _show_stream_selection(self, resolutions):
        """Show stream selection options to user"""
        logger.info(f"Showing {len(resolutions)} stream options for user selection")
        self.awaiting_resolution_selection = True
        self.available_resolutions = resolutions

        # Enrich metadata and add thumbnails for each stream
        for stream in resolutions:
            self._enrich_and_add_thumbnail(stream)

    def _show_unparsed_stream(self, stream_url):
        """Show unparsed stream for user selection"""
        logger.info(f"Showing unparsed stream for user selection: {stream_url}")
        stream_entry = {
            'url': stream_url,
            'bandwidth': 0,
            'resolution': 'unknown',
            'framerate': '',
            'codecs': '',
            'name': 'Stream (unknown quality)'
        }
        self._show_stream_selection([stream_entry])

