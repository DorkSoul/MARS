import re
import logging
import requests

logger = logging.getLogger(__name__)


class PlaylistParser:
    """Handles parsing of HLS master playlists"""

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
    def parse_master_playlist(content):
        """Parse master playlist and extract resolution information"""
        resolutions = []
        lines = content.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Look for stream info lines
            if line.startswith('#EXT-X-STREAM-INF:'):
                # Parse attributes
                attrs = {}
                for attr in line.split(','):
                    if '=' in attr:
                        key, value = attr.split('=', 1)
                        attrs[key.strip()] = value.strip('"')

                # Get the URL from next line
                if i + 1 < len(lines):
                    stream_url = lines[i + 1].strip()

                    if stream_url and not stream_url.startswith('#'):
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

                        resolution_info = {
                            'url': stream_url,
                            'bandwidth': int(attrs.get('BANDWIDTH', 0)),
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

    @staticmethod
    def match_resolution(resolutions, preferred):
        """Find best matching resolution"""
        if not resolutions:
            return None

        preferred_lower = preferred.lower()

        # Try exact match first
        for res in resolutions:
            if res['name'].lower() == preferred_lower:
                logger.info(f"Found exact match for {preferred}: {res['name']}")
                return res

        # Try partial match (e.g., "1080p" matches "1080p60")
        for res in resolutions:
            if preferred_lower in res['name'].lower():
                logger.info(f"Found partial match for {preferred}: {res['name']}")
                return res

        # Special case: "source" means highest quality
        if preferred_lower == 'source':
            logger.info(f"Source requested, returning highest quality: {resolutions[0]['name']}")
            return resolutions[0]

        logger.warning(f"No match found for {preferred}")
        return None
