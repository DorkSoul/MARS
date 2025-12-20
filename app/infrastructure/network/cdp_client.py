"""Chrome DevTools Protocol (CDP) Client - Handles WebSocket communication with Chrome"""

import json
import logging
import websocket
import requests as req_lib

logger = logging.getLogger(__name__)


class CDPClient:
    """Manages Chrome DevTools Protocol WebSocket connection and event handling"""

    def __init__(self):
        """Initialize the CDP client"""
        self.ws = None
        self.ws_url = None
        self.session_id = 1
        self.network_event_handler = None
        self.fetch_event_handler = None

    def setup_connection(self, driver):
        """
        Setup CDP WebSocket connection from Chrome driver

        Args:
            driver: Selenium WebDriver instance

        Returns:
            bool: True if WebSocket URL was obtained, False otherwise
        """
        try:
            # Get the debugger address from Chrome
            debugger_address = None
            if 'goog:chromeOptions' in driver.capabilities:
                debugger_address = driver.capabilities['goog:chromeOptions'].get('debuggerAddress')

            if debugger_address:
                # Query the debugger to get WebSocket URL
                debugger_url = f"http://{debugger_address}/json"
                try:
                    response = req_lib.get(debugger_url, timeout=5)
                    if response.status_code == 200:
                        pages = response.json()
                        if pages and len(pages) > 0:
                            self.ws_url = pages[0].get('webSocketDebuggerUrl')
                            logger.info(f"CDP WebSocket URL obtained")
                            return True
                except Exception as e:
                    logger.warning(f"Failed to get WebSocket URL: {e}")

            # Enable Network domain via execute_cdp_cmd as fallback
            driver.execute_cdp_cmd('Network.enable', {})
            return False

        except Exception as e:
            logger.warning(f"Could not set up CDP: {e}")
            return False

    def set_event_handlers(self, network_handler=None, fetch_handler=None):
        """
        Set callback handlers for CDP events

        Args:
            network_handler: Callable(method, params, ws) for Network.* events
            fetch_handler: Callable(params, ws) for Fetch.requestPaused events
        """
        self.network_event_handler = network_handler
        self.fetch_event_handler = fetch_handler

    def start_listener(self):
        """
        Start the CDP WebSocket listener (blocking call)

        This should be run in a separate thread. It will continuously
        listen for CDP events and route them to registered handlers.
        """
        if not self.ws_url:
            logger.warning("No WebSocket URL available, cannot start listener")
            return

        def on_message(ws, message):
            """Handle incoming CDP messages"""
            try:
                data = json.loads(message)
                method = data.get('method', '')
                params = data.get('params', {})

                # Route Network events
                if method.startswith('Network.'):
                    if self.network_event_handler:
                        self.network_event_handler(method, params, ws)

                # Route Fetch events
                elif method == 'Fetch.requestPaused':
                    if self.fetch_event_handler:
                        self.fetch_event_handler(params, ws)

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"CDP error: {e}")

        def on_error(ws, error):
            logger.error(f"CDP WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            pass

        def on_open(ws):
            self._enable_domains(ws)

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

    def _enable_domains(self, ws):
        """
        Enable CDP domains for monitoring

        Args:
            ws: WebSocket connection
        """
        try:
            # Network domain
            self._send_command(ws, "Network.enable", {
                "maxTotalBufferSize": 100000000,
                "maxResourceBufferSize": 50000000,
                "maxPostDataSize": 50000000
            })

            # Page domain
            self._send_command(ws, "Page.enable", {})

            # Fetch domain (for request interception)
            self._send_command(ws, "Fetch.enable", {
                "patterns": [{"urlPattern": "*", "requestStage": "Request"}]
            })

            # Runtime domain
            self._send_command(ws, "Runtime.enable", {})

        except Exception as e:
            logger.error(f"CDP enable error: {e}")

    def _send_command(self, ws, method, params):
        """
        Send a CDP command via WebSocket

        Args:
            ws: WebSocket connection
            method: CDP method name (e.g., "Network.enable")
            params: Dictionary of parameters
        """
        command = {
            "id": self.session_id,
            "method": method,
            "params": params
        }
        self.session_id += 1
        ws.send(json.dumps(command))

    def send_fetch_continue(self, ws, request_id):
        """
        Send Fetch.continueRequest command

        Args:
            ws: WebSocket connection
            request_id: Request ID to continue
        """
        try:
            self._send_command(ws, "Fetch.continueRequest", {"requestId": request_id})
        except Exception:
            pass

    def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
