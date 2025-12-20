"""
Network traffic monitoring
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


class NetworkMonitorMixin:
    """Network traffic monitoring"""
    def _monitor_network(self):
        """Monitor network traffic for video streams (legacy backup)"""
        while self.is_running and self.driver:
            try:
                logs = self.driver.get_log('performance')

                for entry in logs:
                    try:
                        log_data = json.loads(entry['message'])
                        message = log_data.get('message', {})
                        method = message.get('method', '')

                        if method == 'Network.responseReceived':
                            params = message.get('params', {})
                            response = params.get('response', {})
                            url = response.get('url', '')
                            mime_type = response.get('mimeType', '')

                            if self._is_video_stream(url, mime_type):
                                self._add_detected_stream(url, mime_type)

                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        pass

                time.sleep(0.5)

            except Exception:
                break

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

