"""
Resolution and framerate matching
Mixin for StreamDetector class
"""
import logging
import json
import time
import threading
import websocket
import requests as req_lib

logger = logging.getLogger(__name__)


class StreamMatcherMixin:
    """Resolution and framerate matching"""
    def _match_stream(self, resolutions):
        """Find best matching stream with cascade fallback logic"""
        if not resolutions:
            return None

        # Helper to get numeric values
        def get_resolution_height(res):
            resolution_str = res.get('resolution', '')
            name = res.get('name', '').lower()
            if 'x' in resolution_str:
                try:
                    return int(resolution_str.split('x')[1])
                except: pass
            import re
            match = re.search(r'(\d+)p', name)
            if match:
                return int(match.group(1))
            return res.get('bandwidth', 0) // 1000000

        def get_framerate(res):
            fr = res.get('framerate', '')
            if fr:
                try:
                    return float(str(fr).split('.')[0])
                except: pass
            name = res.get('name', '').lower()
            import re
            match = re.search(r'p(\d+)', name)
            if match:
                return float(match.group(1))
            return 0.0

        # Sort all streams by quality (Resolution DESC, Framerate DESC)
        sorted_streams = sorted(
            resolutions,
            key=lambda x: (get_resolution_height(x), get_framerate(x)),
            reverse=True
        )

        target_res_str = self.resolution.lower().replace('p', '')
        
        # 0. Source/Highest Request
        if target_res_str == 'source':
            logger.info("Match: Source requested, using highest quality.")
            return sorted_streams[0]

        try:
            target_height = int(target_res_str)
        except ValueError:
            target_height = 1080 # Default if parsing fails

        target_fps = None
        if self.framerate in ['60', '30']:
            target_fps = float(self.framerate)

        # 1. Try Perfect Match (Resolution + FPS)
        if target_fps:
            perfect_candidates = []
            for res in sorted_streams:
                h = get_resolution_height(res)
                f = get_framerate(res)
                # Allow small tolerance
                if abs(h - target_height) < 10 and abs(f - target_fps) < 5:
                    perfect_candidates.append(res)
            
            if perfect_candidates:
                logger.info(f"Match: Found perfect match {perfect_candidates[0].get('name')}")
                return perfect_candidates[0]

        # 2. Try Match Resolution (Any FPS)
        res_candidates = []
        for res in sorted_streams:
            h = get_resolution_height(res)
            if abs(h - target_height) < 10:
                res_candidates.append(res)
        
        if res_candidates:
            # Pick highest FPS among matching resolution
            best_res = sorted(res_candidates, key=lambda x: get_framerate(x), reverse=True)[0]
            logger.info(f"Match: Found resolution match {best_res.get('name')} (FPS mismatch or any)")
            return best_res

        # 3. Try Next Resolution Down
        # Find highest resolution that is LOWER than target
        lower_candidates = []
        for res in sorted_streams:
            h = get_resolution_height(res)
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
