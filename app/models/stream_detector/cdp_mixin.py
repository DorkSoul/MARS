"""
Chrome DevTools Protocol handling
Mixin for StreamDetector class
"""
import logging
import json
import time
import threading
import websocket
import requests as req_lib

logger = logging.getLogger(__name__)


class CDPMixin:
    """Chrome DevTools Protocol handling"""
    def _setup_cdp(self):
        """Setup Chrome DevTools Protocol connection"""
        try:
            # Get the debugger address from Chrome
            debugger_address = None
            if 'goog:chromeOptions' in self.driver.capabilities:
                debugger_address = self.driver.capabilities['goog:chromeOptions'].get('debuggerAddress')

            if debugger_address:
                # Query the debugger to get WebSocket URL
                debugger_url = f"http://{debugger_address}/json"
                try:
                    response = req_lib.get(debugger_url, timeout=5)
                    if response.status_code == 200:
                        pages = response.json()
                        if pages and len(pages) > 0:
                            self.ws_url = pages[0].get('webSocketDebuggerUrl')
                except Exception:
                    pass

            # Enable Network domain via execute_cdp_cmd
            self.driver.execute_cdp_cmd('Network.enable', {})

        except Exception as e:
            logger.warning(f"Could not set up CDP: {e}")

    def _cdp_websocket_listener(self):
        """Real-time CDP WebSocket listener"""

        def on_message(ws, message):
            """Handle incoming CDP messages"""
            try:
                data = json.loads(message)
                method = data.get('method', '')
                params = data.get('params', {})

                if method.startswith('Network.'):
                    self._handle_network_event(method, params, ws)
                elif method == 'Fetch.requestPaused':
                    self._handle_fetch_event(params, ws)

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"CDP error: {e}")

        def on_error(ws, error):
            logger.error(f"CDP WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            pass

        def on_open(ws):
            self._cdp_enable_domains(ws)

        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"CDP WebSocket error: {e}")


    def _handle_network_event(self, method, params, ws):
        """Handle Network.* CDP events"""
        url = None
        mime_type = ''

        if method == 'Network.responseReceived':
            response = params.get('response', {})
            url = response.get('url', '')
            mime_type = response.get('mimeType', '')

            if self._is_video_stream(url, mime_type):
                self._add_detected_stream(url, mime_type)

    def _handle_fetch_event(self, params, ws):
        """Handle Fetch.requestPaused CDP events"""
        request = params.get('request', {})
        url = request.get('url', '')
        request_id = params.get('requestId', '')

        if 'm3u8' in url.lower():
            is_likely_master = self._is_likely_master_playlist(url)
            is_likely_media = self._is_likely_media_playlist(url)

            if not is_likely_media and (is_likely_master or not self.detected_streams):
                mime_type = 'application/vnd.apple.mpegurl'
                if self._is_video_stream(url, mime_type):
                    self._add_detected_stream(url, mime_type, stream_type='HLS')

        # Continue the request
        try:
            continue_cmd = {
                "id": self.cdp_session_id,
                "method": "Fetch.continueRequest",
                "params": {"requestId": request_id}
            }
            self.cdp_session_id += 1
            ws.send(json.dumps(continue_cmd))
        except Exception:
            pass

    def _cdp_enable_domains(self, ws):
        """Enable CDP domains for network monitoring"""
        try:
            # Network domain
            enable_cmd = {
                "id": self.cdp_session_id,
                "method": "Network.enable",
                "params": {
                    "maxTotalBufferSize": 100000000,
                    "maxResourceBufferSize": 50000000,
                    "maxPostDataSize": 50000000
                }
            }
            self.cdp_session_id += 1
            ws.send(json.dumps(enable_cmd))

            # Page domain
            page_enable_cmd = {
                "id": self.cdp_session_id,
                "method": "Page.enable",
                "params": {}
            }
            self.cdp_session_id += 1
            ws.send(json.dumps(page_enable_cmd))

            # Fetch domain
            fetch_enable_cmd = {
                "id": self.cdp_session_id,
                "method": "Fetch.enable",
                "params": {
                    "patterns": [{"urlPattern": "*", "requestStage": "Request"}]
                }
            }
            self.cdp_session_id += 1
            ws.send(json.dumps(fetch_enable_cmd))

            # Runtime domain
            runtime_enable_cmd = {
                "id": self.cdp_session_id,
                "method": "Runtime.enable",
                "params": {}
            }
            self.cdp_session_id += 1
            ws.send(json.dumps(runtime_enable_cmd))

        except Exception as e:
            logger.error(f"CDP enable error: {e}")

