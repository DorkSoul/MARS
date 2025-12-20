import time
import json
import logging
import threading
import websocket
import requests as req_lib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import glob

from app.utils import PlaylistParser, MetadataExtractor, ThumbnailGenerator
from .cdp_mixin import CDPMixin
from .network_monitor_mixin import NetworkMonitorMixin
from .stream_parser_mixin import StreamParserMixin
from .stream_matcher_mixin import StreamMatcherMixin
from .download_handler_mixin import DownloadHandlerMixin

logger = logging.getLogger(__name__)


class StreamDetector(CDPMixin, NetworkMonitorMixin, StreamParserMixin, 
                     StreamMatcherMixin, DownloadHandlerMixin):
    """Detects and handles video streams from web pages using browser automation"""

    def __init__(self, browser_id, config, resolution='1080p', framerate='any', auto_download=False, filename=None, output_format='mp4'):
        self.browser_id = browser_id
        self.config = config
        self.driver = None
        self.detected_streams = []
        self.is_running = False
        self.is_closing = False  # Flag to prevent duplicate close logs
        self.download_started = False
        self.thumbnail_data = None
        self.resolution = resolution
        self.framerate = framerate  # 'any', '60', '30'
        self.auto_download = auto_download
        self.filename = filename  # Optional custom filename
        self.output_format = output_format  # Output file format (mp4, mkv, mp3, etc.)
        self.awaiting_resolution_selection = False
        self.available_resolutions = []
        self.selected_stream_url = None
        # WebSocket CDP connection
        self.ws = None
        self.ws_url = None
        self.cdp_session_id = 1
        # Callback for when download needs to be started
        self.download_callback = None

    def set_download_callback(self, callback):
        """Set callback function for starting downloads"""
        self.download_callback = callback

    def start_browser(self, url):
        """Start Chrome with DevTools Protocol enabled"""
        max_retries = 2
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Extract domain for cleaner logging
                from urllib.parse import urlparse
                domain = urlparse(url).netloc or url
                logger.info(f"Starting Chrome for {domain}")

                chrome_options = Options()
                
                # Essential flags for Docker
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-setuid-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')

                # Fix "Chrome did not shut down correctly" and session restore issues
                try:
                    prefs_path = os.path.join(self.config.CHROME_USER_DATA_DIR, 'Default', 'Preferences')
                    if os.path.exists(prefs_path):
                        with open(prefs_path, 'r', encoding='utf-8') as f:
                            prefs = json.load(f)
                        
                        # Reset crash flags and session restore settings
                        changed = False
                        
                        # Reset exit_type to Normal
                        if 'profile' in prefs:
                            if prefs['profile'].get('exit_type') != 'Normal':
                                prefs['profile']['exit_type'] = 'Normal'
                                changed = True
                            # Also reset exited_cleanly flag
                            if prefs['profile'].get('exited_cleanly') != True:
                                prefs['profile']['exited_cleanly'] = True
                                changed = True
                        
                        # Disable session restore (prevents blank window with highlighted URL)
                        if 'session' in prefs:
                            if prefs['session'].get('restore_on_startup') != 5:  # 5 = don't restore
                                prefs['session']['restore_on_startup'] = 5
                                changed = True
                        
                        # Also clear the startup URLs (another session restore mechanism)
                        if 'session' in prefs and 'startup_urls' in prefs['session']:
                            if prefs['session']['startup_urls']:
                                prefs['session']['startup_urls'] = []
                                changed = True
                        
                        if changed:
                            logger.debug("Resetting Chrome crash flag and session restore settings in Preferences")
                            with open(prefs_path, 'w', encoding='utf-8') as f:
                                json.dump(prefs, f)
                except Exception as prefs_error:
                    logger.warning(f"Could not reset Chrome preferences: {prefs_error}")

                # Enable remote debugging for CDP WebSocket (port 0 = auto-assign)
                chrome_options.add_argument('--remote-debugging-port=0')
                # Allow WebSocket connections to CDP from any origin
                chrome_options.add_argument('--remote-allow-origins=*')

                # GPU and rendering
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--disable-software-rasterizer')

                # Optimization flags
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-background-networking')
                chrome_options.add_argument('--disable-sync')
                chrome_options.add_argument('--disable-translate')
                chrome_options.add_argument('--disable-default-apps')
                chrome_options.add_argument('--disable-notifications')
                
                # Prevent session restore issues (blank window with highlighted URL)
                chrome_options.add_argument('--disable-session-crashed-bubble')
                chrome_options.add_argument('--disable-infobars')
                chrome_options.add_argument('--no-first-run')
                # Additional flags to prevent session/tab restore
                chrome_options.add_argument('--no-default-browser-check')
                chrome_options.add_argument('--disable-restore-session-state')
                chrome_options.add_argument('--disable-background-timer-throttling')
                # Start with about:blank to prevent session restore race condition
                chrome_options.add_argument('about:blank')

                # User data directory for cookie persistence
                chrome_options.add_argument(f'--user-data-dir={self.config.CHROME_USER_DATA_DIR}')

                # Logging
                chrome_options.add_argument('--enable-logging')
                chrome_options.add_argument('--v=1')

                chrome_options.add_experimental_option('w3c', True)
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

                # Set preferences for cookie persistence
                chrome_prefs = {
                    # Enable cookies and set to keep them
                    "profile.default_content_setting_values.cookies": 1,  # 1 = allow all cookies
                    "profile.block_third_party_cookies": False,
                    # Ensure session is saved on exit
                    "profile.exit_type": "Normal",
                    "profile.exited_cleanly": True,
                    # Don't clear cookies on exit
                    "profile.default_content_settings.cookies": 1,
                    # Keep cookies after browser closes
                    "profile.cookie_controls_mode": 0,  # 0 = allow all
                }
                chrome_options.add_experimental_option('prefs', chrome_prefs)

                # Enable performance logging to capture network events
                chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

                logger.debug("Initializing ChromeDriver...")
                service = Service(
                    self.config.CHROMEDRIVER_PATH,
                    log_output=self.config.CHROMEDRIVER_LOG_PATH
                )

                try:
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.debug("Chrome started successfully")
                    
                    # Set page load timeout to prevent hangs
                    self.driver.set_page_load_timeout(60)
                    
                except Exception as driver_error:
                    logger.error(f"Failed to create Chrome webdriver: {driver_error}")

                    # If this is the first attempt and error mentions "Chrome instance exited"
                    if retry_count == 0 and "Chrome instance exited" in str(driver_error):
                        logger.warning("Chrome failed to start with user-data-dir, cleaning lock files and retrying...")
                        retry_count += 1

                        # Clean up problematic lock files in user-data-dir
                        try:
                            lock_files = glob.glob(os.path.join(self.config.CHROME_USER_DATA_DIR, '**/SingletonLock'), recursive=True)
                            lock_files.extend(glob.glob(os.path.join(self.config.CHROME_USER_DATA_DIR, '**/lockfile'), recursive=True))

                            for lock_file in lock_files:
                                try:
                                    os.remove(lock_file)
                                    logger.info(f"Removed lock file: {lock_file}")
                                except Exception as remove_error:
                                    logger.warning(f"Could not remove {lock_file}: {remove_error}")
                        except Exception as cleanup_error:
                            logger.warning(f"Error during lock file cleanup: {cleanup_error}")

                        # Small delay to let file system catch up
                        time.sleep(1)
                        continue  # Retry
                    else:
                        raise

                self.driver.set_window_size(1920, 1080)
                break  # Success, exit retry loop

            except WebDriverException as e:
                logger.error(f"WebDriver error starting browser: {e}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    logger.info(f"Retrying... attempt {retry_count + 1}/{max_retries}")
                    time.sleep(2)
                    continue
                logger.error(f"Error details: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error starting browser: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return False

        if retry_count >= max_retries:
            logger.error("Failed to start Chrome after all retry attempts")
            return False

        # Get CDP WebSocket URL for real-time event monitoring
        self._setup_cdp()

        self.is_running = True

        # Start WebSocket CDP listener BEFORE navigating to catch initial requests
        if self.ws_url:
            threading.Thread(target=self._cdp_websocket_listener, daemon=True).start()
            # Give WebSocket a moment to connect
            time.sleep(0.5)
        else:
            logger.warning("No WebSocket URL available, falling back to polling only")

        # Start monitoring network traffic (legacy polling as backup)
        threading.Thread(target=self._monitor_network, daemon=True).start()

        # Navigate to URL with JS navigation to avoid session restore issues
        logger.debug(f"Navigating to {url}")
        max_nav_attempts = 3
        for attempt in range(max_nav_attempts):
            try:
                # First, navigate to about:blank to reset any session restore state
                if attempt == 0:
                    self.driver.get('about:blank')
                    time.sleep(0.5)
                
                # Use JavaScript navigation for more forceful control
                try:
                    self.driver.execute_script(f'window.location.href = "{url}";')
                except Exception:
                    self.driver.get(url)
                
                time.sleep(1)
                current_url = self.driver.current_url
                
                # Verify we're not still on about:blank
                if current_url == 'about:blank' or 'about:blank' in current_url:
                    continue
                
                # Check if body has content (not just a blank white page)
                try:
                    body_len = self.driver.execute_script('return document.body ? document.body.innerHTML.length : 0')
                    if body_len < 100:
                        self.driver.refresh()
                        time.sleep(2)
                except Exception:
                    pass
                
                # Wait for page to be ready
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda d: d.execute_script('return document.readyState') in ['interactive', 'complete']
                    )
                except TimeoutException:
                    pass
                break
                    
            except Exception as e:
                logger.error(f"Navigation error on attempt {attempt + 1}: {e}")
                if attempt < max_nav_attempts - 1:
                    time.sleep(1)
                else:
                    logger.error("All navigation attempts failed")
             
        return True

    def close(self):
        """Close the browser gracefully"""
        # Check if already closing to prevent duplicate logs
        if self.is_closing:
            return

        self.is_closing = True
        self.is_running = False

        # Close WebSocket connection
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

        if self.driver:
            try:
                # Graceful shutdown process to prevent "Chrome did not shut down correctly" message
                logger.info(f"Closing browser {self.browser_id}...")

                # Step 1: Navigate to about:blank to stop any active page loading/streaming
                try:
                    self.driver.get('about:blank')
                    time.sleep(0.5)
                except Exception:
                    pass

                # Step 2: Execute JavaScript to clear any local storage or session data that might cause issues
                try:
                    self.driver.execute_script("""
                        try {
                            // Clear any pending timers or intervals
                            var highestTimeoutId = setTimeout(";");
                            for (var i = 0; i < highestTimeoutId; i++) {
                                clearTimeout(i);
                            }
                            var highestIntervalId = setInterval(";");
                            for (var i = 0; i < highestIntervalId; i++) {
                                clearInterval(i);
                            }
                        } catch(e) {}
                    """)
                except Exception:
                    pass

                # Step 3: Quit the driver and wait for Chrome to fully exit
                self.driver.quit()
                # Give Chrome time to fully terminate and write its preferences
                time.sleep(0.8)

                # Step 4: AFTER Chrome has quit, fix the preferences file for next startup
                try:
                    prefs_path = os.path.join(self.config.CHROME_USER_DATA_DIR, 'Default', 'Preferences')
                    if os.path.exists(prefs_path):
                        # Read and update preferences
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                with open(prefs_path, 'r', encoding='utf-8') as f:
                                    prefs = json.load(f)

                                # Mark as clean exit for next startup
                                if 'profile' not in prefs:
                                    prefs['profile'] = {}
                                prefs['profile']['exit_type'] = 'Normal'
                                prefs['profile']['exited_cleanly'] = True

                                with open(prefs_path, 'w', encoding='utf-8') as f:
                                    json.dump(prefs, f)
                                logger.debug("Set Chrome exit flags to Normal for next startup")
                                break
                            except (IOError, OSError) as file_error:
                                # File might be locked, wait and retry
                                if retry < max_retries - 1:
                                    time.sleep(0.3)
                                    continue
                                else:
                                    raise file_error
                    else:
                        logger.warning(f"Preferences file not found at {prefs_path}")
                except Exception as prefs_error:
                    logger.warning(f"Could not set Chrome exit flags: {prefs_error}")

                logger.debug(f"Browser {self.browser_id} closed gracefully")

            except Exception as e:
                logger.error(f"Error closing browser: {e}")

    def get_status(self):
        """Get current status"""
        return {
            'browser_id': self.browser_id,
            'is_running': self.is_running,
            'download_started': self.download_started,
            'detected_streams': len(self.detected_streams),
            'thumbnail': self.thumbnail_data,
            'latest_stream': self.detected_streams[-1] if self.detected_streams else None,
            'awaiting_resolution_selection': self.awaiting_resolution_selection,
            'available_resolutions': self.available_resolutions,
            'selected_stream_metadata': getattr(self, 'selected_stream_metadata', None)
        }
