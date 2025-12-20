"""Network Event Handler - Processes CDP network events and detects video streams"""

import json
import logging
import time

logger = logging.getLogger(__name__)


class NetworkEventHandler:
    """Handles network events from CDP and legacy performance logs"""

    def __init__(self, stream_filter, stream_callback):
        """
        Initialize the network event handler

        Args:
            stream_filter: StreamFilter instance for detecting video streams
            stream_callback: Callable(url, mime_type, stream_type) called when stream is detected
        """
        self.stream_filter = stream_filter
        self.stream_callback = stream_callback

    def handle_network_event(self, method, params, ws):
        """
        Handle Network.* CDP events

        Args:
            method: CDP method name (e.g., "Network.responseReceived")
            params: Event parameters
            ws: WebSocket connection (for sending commands if needed)
        """
        if method == 'Network.responseReceived':
            response = params.get('response', {})
            url = response.get('url', '')
            mime_type = response.get('mimeType', '')

            if self.stream_filter.is_video_stream(url, mime_type):
                stream_type = self.stream_filter.get_stream_type(url)
                self.stream_callback(url, mime_type, stream_type)

    def handle_fetch_event(self, params, ws):
        """
        Handle Fetch.requestPaused CDP events

        Args:
            params: Event parameters
            ws: WebSocket connection for sending continue command
        """
        request = params.get('request', {})
        url = request.get('url', '')
        request_id = params.get('requestId', '')

        # Check for HLS playlists
        if 'm3u8' in url.lower():
            is_likely_master = self.stream_filter.is_likely_master_playlist(url)
            is_likely_media = self.stream_filter.is_likely_media_playlist(url)

            # Only capture master playlists, not media segments
            if not is_likely_media and (is_likely_master or self.stream_callback):
                mime_type = 'application/vnd.apple.mpegurl'
                if self.stream_filter.is_video_stream(url, mime_type):
                    self.stream_callback(url, mime_type, 'HLS')

        # Continue the request (must not block the request)
        if request_id and ws:
            try:
                # Import here to avoid circular dependency
                from app.infrastructure.network.cdp_client import CDPClient
                # Use static method to send continue command
                continue_cmd = {
                    "id": getattr(ws, 'session_id', 1),
                    "method": "Fetch.continueRequest",
                    "params": {"requestId": request_id}
                }
                ws.send(json.dumps(continue_cmd))
            except Exception:
                pass

    def monitor_performance_logs(self, driver, is_running_func):
        """
        Legacy network monitoring via performance logs (backup method)

        Args:
            driver: Selenium WebDriver instance
            is_running_func: Callable that returns True while monitoring should continue
        """
        while is_running_func() and driver:
            try:
                logs = driver.get_log('performance')

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

                            if self.stream_filter.is_video_stream(url, mime_type):
                                stream_type = self.stream_filter.get_stream_type(url)
                                self.stream_callback(url, mime_type, stream_type)

                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        pass

                time.sleep(0.5)

            except Exception:
                break
