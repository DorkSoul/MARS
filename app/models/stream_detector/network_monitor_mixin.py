"""
Network traffic monitoring
Mixin for StreamDetector class

Stream classification and detection helpers (_is_video_stream,
_add_detected_stream, etc.) live in StreamParserMixin.
"""
import logging
import json
import time

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
