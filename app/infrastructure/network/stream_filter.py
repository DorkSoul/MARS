"""Stream Filter - Detects and filters video stream URLs"""

import logging

logger = logging.getLogger(__name__)


class StreamFilter:
    """Filters and identifies video stream URLs from network traffic"""

    # Playlist extensions we care about
    PLAYLIST_EXTENSIONS = ['.m3u8', '.mpd']

    # MIME types for playlists
    PLAYLIST_MIME_TYPES = [
        'application/vnd.apple.mpegurl',
        'application/dash+xml',
        'application/x-mpegurl',
        'vnd.apple.mpegurl'
    ]

    # Segment extensions to filter out
    SEGMENT_EXTENSIONS = ['.ts', '.m4s']

    # Keywords to filter out (ads, tracking)
    FILTER_KEYWORDS = ['doubleclick', 'analytics', 'tracking']

    def is_video_stream(self, url, mime_type=''):
        """
        Check if URL is a video stream - ONLY playlists, not segments

        Args:
            url: The URL to check
            mime_type: Optional MIME type from response headers

        Returns:
            bool: True if URL is a video stream playlist
        """
        url_lower = url.lower()

        # Filter out individual segment files
        if any(url_lower.endswith(ext) for ext in self.SEGMENT_EXTENSIONS):
            return False

        if '/segment/' in url_lower:
            return False

        # HIGH PRIORITY: Twitch HLS API endpoint
        if 'usher.ttvnw.net' in url_lower and '.m3u8' in url_lower:
            return True

        # Check for playlist extensions
        if any(url_lower.endswith(ext) or f'{ext}?' in url_lower for ext in self.PLAYLIST_EXTENSIONS):
            # Filter out ads and tracking
            if any(keyword in url_lower for keyword in self.FILTER_KEYWORDS):
                return False
            return True

        # Check for playlist in path
        if 'playlist' in url_lower and '.m3u8' in url_lower:
            return True

        # Check MIME type for playlists
        mime_type_lower = mime_type.lower()
        if any(mime in mime_type_lower for mime in self.PLAYLIST_MIME_TYPES):
            return True

        return False

    def is_likely_master_playlist(self, url):
        """
        Check if URL is likely a master playlist

        Args:
            url: The URL to check

        Returns:
            bool: True if URL appears to be a master playlist
        """
        url_lower = url.lower()
        return (
            'usher' in url_lower or
            'master' in url_lower or
            '/playlist.m3u8' in url_lower or
            '/index.m3u8' in url_lower or
            'api' in url_lower
        )

    def is_likely_media_playlist(self, url):
        """
        Check if URL is likely a media playlist (not master)

        Args:
            url: The URL to check

        Returns:
            bool: True if URL appears to be a media/segment playlist
        """
        url_lower = url.lower()
        return (
            '/chunklist' in url_lower or
            '/media_' in url_lower or
            '/segment' in url_lower
        )

    def get_stream_type(self, url):
        """
        Determine stream type from URL

        Args:
            url: The URL to analyze

        Returns:
            str: Stream type ('HLS', 'DASH', 'MP4', or 'UNKNOWN')
        """
        url_lower = url.lower()

        if '.m3u8' in url_lower:
            return 'HLS'
        elif '.mpd' in url_lower:
            return 'DASH'
        elif '.mp4' in url_lower:
            return 'MP4'
        else:
            return 'UNKNOWN'
