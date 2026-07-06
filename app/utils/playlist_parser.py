import re
import logging
from urllib.parse import urljoin
import requests

logger = logging.getLogger(__name__)


class PlaylistParser:
    """Handles parsing of HLS master playlists"""

    # Matches KEY=VALUE pairs where VALUE may be a quoted string containing
    # commas (e.g. CODECS="avc1.64001f,mp4a.40.2") — a plain split(',') would
    # truncate those values.
    _ATTR_RE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')

    @staticmethod
    def fetch_master_playlist(url):
        """Fetch and return master playlist content"""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.error(f"Failed to fetch master playlist: {e}")
            return None

    @staticmethod
    def parse_master_playlist(content, base_url=None):
        """Parse master playlist and extract resolution information.

        base_url (the master playlist URL) is used to resolve relative
        variant URIs, which are common in HLS playlists.
        """
        resolutions = []
        lines = content.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Look for stream info lines
            if line.startswith('#EXT-X-STREAM-INF:'):
                attrs = {
                    key: value.strip('"')
                    for key, value in PlaylistParser._ATTR_RE.findall(line.split(':', 1)[1])
                }

                # Get the URL from next line
                if i + 1 < len(lines):
                    stream_url = lines[i + 1].strip()

                    if stream_url and not stream_url.startswith('#'):
                        if base_url:
                            stream_url = urljoin(base_url, stream_url)

                        # Get base name and framerate
                        base_name = attrs.get('IVS-NAME', attrs.get('STABLE-VARIANT-ID', ''))
                        framerate = attrs.get('FRAME-RATE', '')

                        # Normalize name to always include framerate
                        if framerate and base_name:
                            # Extract numeric framerate (e.g., "60.000" -> "60")
                            fps_numeric = framerate.split('.')[0] if '.' in str(framerate) else str(framerate)
                            # Only append if not already at the end (e.g., "1080p60" already has 60)
                            if not re.search(r'p\d+$', base_name):
                                base_name = f"{base_name}{fps_numeric}"

                        try:
                            bandwidth = int(attrs.get('BANDWIDTH', 0))
                        except ValueError:
                            bandwidth = 0

                        resolution_info = {
                            'url': stream_url,
                            'bandwidth': bandwidth,
                            'resolution': attrs.get('RESOLUTION', ''),
                            'framerate': framerate,
                            'codecs': attrs.get('CODECS', ''),
                            'name': base_name
                        }

                        resolutions.append(resolution_info)

            i += 1

        # Sort by bandwidth (highest first)
        resolutions.sort(key=lambda x: x['bandwidth'], reverse=True)

        # Log sorted resolutions for debugging
        logger.info(f"Parsed {len(resolutions)} resolutions, sorted by bandwidth:")
        for idx, res in enumerate(resolutions):
            logger.info(f"  [{idx}] {res['name']} - {res['resolution']} @ {res.get('framerate', '?')}fps - Bandwidth: {res['bandwidth']}")

        return resolutions
