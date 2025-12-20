"""Stream matching strategy for finding the best stream based on resolution and framerate"""

import re
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class StreamMatcher:
    """
    Strategy pattern implementation for matching video streams based on resolution and framerate.

    Uses a cascade fallback matching logic:
    1. Source/Highest quality if 'source' is requested
    2. Perfect match (resolution + framerate)
    3. Resolution match (any framerate)
    4. Next lower resolution
    5. Highest available quality
    """

    def __init__(self, target_resolution: str, target_framerate: str = 'any'):
        """
        Initialize the stream matcher with target criteria.

        Args:
            target_resolution: Target resolution (e.g., '1080p', '720p', 'source')
            target_framerate: Target framerate (e.g., 'any', '60', '30')
        """
        self.target_resolution = target_resolution
        self.target_framerate = target_framerate

    def match_stream(self, resolutions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find best matching stream with cascade fallback logic.

        Args:
            resolutions: List of stream dictionaries containing resolution metadata

        Returns:
            Best matching stream dictionary or None if no resolutions available
        """
        if not resolutions:
            return None

        # Sort all streams by quality (Resolution DESC, Framerate DESC)
        sorted_streams = sorted(
            resolutions,
            key=lambda x: (self.get_resolution_height(x), self.get_framerate(x)),
            reverse=True
        )

        target_res_str = self.target_resolution.lower().replace('p', '')

        # 0. Source/Highest Request
        if target_res_str == 'source':
            logger.info("Match: Source requested, using highest quality.")
            return sorted_streams[0]

        try:
            target_height = int(target_res_str)
        except ValueError:
            target_height = 1080 # Default if parsing fails

        target_fps = None
        if self.target_framerate in ['60', '30']:
            target_fps = float(self.target_framerate)

        # 1. Try Perfect Match (Resolution + FPS)
        if target_fps:
            perfect_candidates = []
            for res in sorted_streams:
                h = self.get_resolution_height(res)
                f = self.get_framerate(res)
                # Allow small tolerance
                if abs(h - target_height) < 10 and abs(f - target_fps) < 5:
                    perfect_candidates.append(res)

            if perfect_candidates:
                logger.info(f"Match: Found perfect match {perfect_candidates[0].get('name')}")
                return perfect_candidates[0]

        # 2. Try Match Resolution (Any FPS)
        res_candidates = []
        for res in sorted_streams:
            h = self.get_resolution_height(res)
            if abs(h - target_height) < 10:
                res_candidates.append(res)

        if res_candidates:
            # Pick highest FPS among matching resolution
            best_res = sorted(res_candidates, key=lambda x: self.get_framerate(x), reverse=True)[0]
            logger.info(f"Match: Found resolution match {best_res.get('name')} (FPS mismatch or any)")
            return best_res

        # 3. Try Next Resolution Down
        # Find highest resolution that is LOWER than target
        lower_candidates = []
        for res in sorted_streams:
            h = self.get_resolution_height(res)
            if h < target_height:
                lower_candidates.append(res)

        if lower_candidates:
            # Already sorted by quality, so first one is the "highest of the lower"
            best_lower = lower_candidates[0]
            logger.info(f"Match: Fallback to lower resolution {best_lower.get('name')}")
            return best_lower

        # 4. Fallback to Any (Highest Available)
        logger.info(f"Match: Fallback to highest available {sorted_streams[0].get('name')}")
        return sorted_streams[0]

    def get_resolution_height(self, res: Dict[str, Any]) -> int:
        """
        Extract numeric height value from stream resolution metadata.

        Tries multiple strategies:
        1. Parse from 'resolution' field (e.g., '1920x1080' -> 1080)
        2. Parse from 'name' field (e.g., '1080p' -> 1080)
        3. Fallback to bandwidth-based estimation

        Args:
            res: Stream dictionary containing resolution metadata

        Returns:
            Resolution height as integer
        """
        resolution_str = res.get('resolution', '')
        name = res.get('name', '').lower()

        # Try to parse from resolution field (e.g., '1920x1080')
        if 'x' in resolution_str:
            try:
                return int(resolution_str.split('x')[1])
            except:
                pass

        # Try to parse from name field (e.g., '1080p')
        match = re.search(r'(\d+)p', name)
        if match:
            return int(match.group(1))

        # Fallback to bandwidth-based estimation
        return res.get('bandwidth', 0) // 1000000

    def get_framerate(self, res: Dict[str, Any]) -> float:
        """
        Extract numeric framerate value from stream metadata.

        Tries multiple strategies:
        1. Parse from 'framerate' field
        2. Parse from 'name' field (e.g., '1080p60' -> 60)
        3. Default to 0.0 if unavailable

        Args:
            res: Stream dictionary containing framerate metadata

        Returns:
            Framerate as float
        """
        # Try to parse from framerate field
        fr = res.get('framerate', '')
        if fr:
            try:
                return float(str(fr).split('.')[0])
            except:
                pass

        # Try to parse from name field (e.g., '1080p60')
        name = res.get('name', '').lower()
        match = re.search(r'p(\d+)', name)
        if match:
            return float(match.group(1))

        return 0.0
