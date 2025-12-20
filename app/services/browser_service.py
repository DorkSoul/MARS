import os
import time
import logging
import subprocess
import shutil
import threading
import queue
from app.models import StreamDetector

logger = logging.getLogger(__name__)


class BrowserService:
    """Manages browser instances and stream detection"""

    def __init__(self, config, download_service):
        self.config = config
        self.download_service = download_service
        self.active_browsers = {}

        # Queue for browser launch requests
        self.browser_queue = queue.Queue()
        self.queue_processor_thread = None
        self.queue_running = False
        self.queue_lock = threading.Lock()

        # Start queue processor
        self._start_queue_processor()

    def start_browser(self, url, browser_id, resolution='1080p', framerate='any', auto_download=False, filename=None, output_format='mp4'):
        """
        Queue a browser instance for stream detection.

        This method adds the browser launch request to a queue and waits for it to complete.
        The queue ensures that only one Chrome window is active at a time, preventing cookie conflicts.
        """
        # Create a threading event to signal completion
        completion_event = threading.Event()
        result_container = {'success': False, 'detector': None}

        # Package the request
        request = {
            'url': url,
            'browser_id': browser_id,
            'resolution': resolution,
            'framerate': framerate,
            'auto_download': auto_download,
            'filename': filename,
            'output_format': output_format,
            'completion_event': completion_event,
            'result': result_container
        }

        # Add placeholder to active_browsers to show "queued" status
        with self.queue_lock:
            self.active_browsers[browser_id] = {
                'status': 'queued',
                'url': url,
                'resolution': resolution,
                'framerate': framerate
            }

        # Add to queue
        logger.info(f"Queueing browser launch for {browser_id}")
        self.browser_queue.put(request)

        # Wait for completion
        completion_event.wait()

        return result_container['success'], result_container['detector']

    def _start_queue_processor(self):
        """Start the background thread that processes browser launch requests"""
        if self.queue_running:
            return

        self.queue_running = True
        self.queue_processor_thread = threading.Thread(target=self._process_browser_queue, daemon=True)
        self.queue_processor_thread.start()
        logger.info("Browser queue processor started")

    def _process_browser_queue(self):
        """Background thread that processes browser launch requests one by one"""
        logger.info("Browser queue processor thread running")

        while self.queue_running:
            try:
                # Wait for a request with timeout to allow checking queue_running flag
                try:
                    request = self.browser_queue.get(timeout=1)
                except queue.Empty:
                    continue

                browser_id = request['browser_id']

                # Update status from 'queued' to 'launching'
                with self.queue_lock:
                    if browser_id in self.active_browsers and isinstance(self.active_browsers[browser_id], dict):
                        self.active_browsers[browser_id]['status'] = 'launching'
                        logger.info(f"Launching {browser_id} (was queued)")

                # Ensure all previous Chrome instances are fully closed
                self._ensure_chrome_closed()

                # Now launch the browser
                success, detector = self._launch_browser_internal(
                    url=request['url'],
                    browser_id=request['browser_id'],
                    resolution=request['resolution'],
                    framerate=request['framerate'],
                    auto_download=request['auto_download'],
                    filename=request['filename'],
                    output_format=request['output_format']
                )

                # Store result
                request['result']['success'] = success
                request['result']['detector'] = detector

                # Signal completion
                request['completion_event'].set()

                # Mark task as done
                self.browser_queue.task_done()

            except Exception as e:
                logger.error(f"Error in browser queue processor: {e}")
                # Still signal completion even on error
                if 'request' in locals() and request:
                    request['completion_event'].set()

    def _ensure_chrome_closed(self):
        """
        Ensure all Chrome processes and browsers are fully closed before starting a new one.
        Waits for a few extra seconds to be absolutely sure.
        """
        # Close all active browsers tracked by this service (skip queued ones)
        browsers_to_close = []

        with self.queue_lock:
            # Create a snapshot of browsers to close (thread-safe)
            for bid, browser in list(self.active_browsers.items()):
                # Only close actual browsers, not queued placeholders
                if not isinstance(browser, dict):
                    browsers_to_close.append(bid)

        if browsers_to_close:
            logger.info("Closing all active browsers before launching new one...")
            for bid in browsers_to_close:
                try:
                    self.close_browser(bid)
                except Exception as e:
                    logger.warning(f"Error closing browser {bid}: {e}")

        # Wait for Chrome processes to fully terminate
        time.sleep(2)

        # Check if Chrome processes are still running
        max_wait = 10  # Maximum 10 seconds to wait
        wait_count = 0

        while wait_count < max_wait:
            try:
                # Check for Chrome processes (platform-specific)
                if os.name == 'nt':  # Windows
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
                                          capture_output=True, text=True, timeout=2)
                    chrome_running = 'chrome.exe' in result.stdout
                else:  # Linux/Mac
                    result = subprocess.run(['pgrep', '-f', 'chrome'],
                                          capture_output=True, text=True, timeout=2)
                    chrome_running = len(result.stdout.strip()) > 0

                if not chrome_running:
                    break

                time.sleep(1)
                wait_count += 1

            except Exception as e:
                logger.debug(f"Error checking Chrome processes: {e}")
                break

        # Add a few extra seconds buffer to be absolutely sure
        time.sleep(3)
        logger.info("Chrome ready to launch")

    def _launch_browser_internal(self, url, browser_id, resolution='1080p', framerate='any', auto_download=False, filename=None, output_format='mp4'):
        """Internal method to actually launch the browser (called by queue processor)"""
        detector = StreamDetector(
            browser_id,
            self.config,
            resolution,
            framerate,
            auto_download,
            filename,
            output_format
        )

        # Set download callback
        detector.set_download_callback(self.download_service.start_download)

        with self.queue_lock:
            self.active_browsers[browser_id] = detector

        if detector.start_browser(url):
            return True, detector
        else:
            with self.queue_lock:
                if browser_id in self.active_browsers:
                    del self.active_browsers[browser_id]
            return False, None

    def close_browser(self, browser_id):
        """Close a specific browser instance"""
        with self.queue_lock:
            if browser_id not in self.active_browsers:
                return False

            detector = self.active_browsers[browser_id]
            # Check if it's a dict (queued) or StreamDetector object (active)
            if isinstance(detector, dict):
                # Just remove from dict - it's still queued, hasn't launched yet
                del self.active_browsers[browser_id]
                return True

        # Close the detector outside the lock to avoid deadlock
        # (detector.close() might do blocking operations)
        try:
            detector.close()
        except Exception as e:
            logger.error(f"Error closing browser {browser_id}: {e}")

        with self.queue_lock:
            # Remove from dict after closing
            if browser_id in self.active_browsers:
                del self.active_browsers[browser_id]

        return True

    def get_browser_status(self, browser_id):
        """Get status of a specific browser"""
        with self.queue_lock:
            if browser_id not in self.active_browsers:
                return None

            browser = self.active_browsers[browser_id]
            # Check if it's a dict (queued) or StreamDetector object (active)
            if isinstance(browser, dict):
                # Return the queued status (make a copy to avoid thread issues)
                return browser.copy()
            else:
                # It's a StreamDetector, get its status
                # (call get_status outside the lock to avoid potential deadlock)
                detector = browser

        # Call get_status outside the lock
        try:
            return detector.get_status()
        except Exception as e:
            logger.error(f"Error getting browser status for {browser_id}: {e}")
            return None

    def get_browser(self, browser_id):
        """Get a browser instance"""
        with self.queue_lock:
            return self.active_browsers.get(browser_id)

    def select_resolution(self, browser_id, stream):
        """Handle manual resolution selection"""
        with self.queue_lock:
            if browser_id not in self.active_browsers:
                return False, "Browser not found"

            detector = self.active_browsers[browser_id]

            # Check if browser is still queued
            if isinstance(detector, dict):
                return False, "Browser is queued and not yet launched"

        logger.info(f"User selected resolution: {stream.get('name')}")

        # Enrich metadata before download
        from app.utils import MetadataExtractor
        MetadataExtractor.enrich_stream_metadata(stream)

        # Clear awaiting state
        detector.awaiting_resolution_selection = False

        # Start download
        detector._start_download_with_stream(stream)

        return True, f'Starting download for {stream.get("name")}'

    def select_stream(self, browser_id, stream_url):
        """Handle manual stream selection"""
        with self.queue_lock:
            if browser_id not in self.active_browsers:
                return False, "Browser not found"

            detector = self.active_browsers[browser_id]

            # Check if browser is still queued
            if isinstance(detector, dict):
                return False, "Browser is queued and not yet launched"

        # Find stream object
        selected_stream = None
        for res in detector.available_resolutions:
            if res['url'] == stream_url:
                selected_stream = res
                break

        if not selected_stream:
            selected_stream = {
                'url': stream_url,
                'name': 'selected_stream',
                'resolution': '',
                'framerate': '',
                'codecs': ''
            }

        stream_name = selected_stream.get('name', 'selected_stream')

        # Enrich metadata
        from app.utils import MetadataExtractor
        MetadataExtractor.enrich_stream_metadata(selected_stream)

        # Clear awaiting state
        detector.awaiting_resolution_selection = False

        # Start download
        detector._start_download_with_url(stream_url, stream_name, selected_stream)

        return True, f'Starting download for {stream_name}'

    def clear_cookies(self):
        """Clear Chrome cookies and profile data"""
        try:
            logger.info("Clear cookies requested")

            # Close all active browsers
            browsers_to_close = list(self.active_browsers.keys())
            for browser_id in browsers_to_close:
                try:
                    self.close_browser(browser_id)
                    logger.info(f"Closed browser {browser_id}")
                except Exception as e:
                    logger.error(f"Error closing browser {browser_id}: {e}")

            # Force kill Chrome processes
            try:
                subprocess.run(['pkill', '-9', 'chrome'], check=False, timeout=5)
                subprocess.run(['pkill', '-9', 'chromedriver'], check=False, timeout=5)
            except Exception:
                pass

            # Wait for processes to terminate
            time.sleep(3)

            if os.path.exists(self.config.CHROME_USER_DATA_DIR):
                try:

                    cleared_count = 0
                    failed_count = 0

                    for item in os.listdir(self.config.CHROME_USER_DATA_DIR):
                        item_path = os.path.join(self.config.CHROME_USER_DATA_DIR, item)
                        try:
                            if os.path.isfile(item_path) or os.path.islink(item_path):
                                os.unlink(item_path)
                                cleared_count += 1
                            elif os.path.isdir(item_path):
                                try:
                                    shutil.rmtree(item_path)
                                    cleared_count += 1
                                except OSError:
                                    # Try to clear contents
                                    for root, dirs, files in os.walk(item_path, topdown=False):
                                        for name in files:
                                            try:
                                                os.remove(os.path.join(root, name))
                                            except:
                                                pass
                                        for name in dirs:
                                            try:
                                                os.rmdir(os.path.join(root, name))
                                            except:
                                                pass
                                    cleared_count += 1
                        except Exception as item_error:
                            logger.error(f"Failed to remove {item}: {item_error}")
                            failed_count += 1

                    logger.info(f"Chrome data cleared: {cleared_count} items")

                    return True, f'Cookies cleared: {cleared_count} items removed'

                except Exception as e:
                    logger.error(f"Error clearing Chrome data: {e}")
                    return False, f'Failed to clear Chrome data: {str(e)}'
            else:
                os.makedirs(self.config.CHROME_USER_DATA_DIR, exist_ok=True)
                return True, 'Chrome data directory created (was not present)'

        except Exception as e:
            logger.error(f"Clear cookies error: {e}")
            return False, str(e)

    def check_chrome_installation(self):
        """Check Chrome and ChromeDriver installation"""
        logger.info("Checking Chrome installation...")
        try:
            # Check Chrome
            chrome_result = subprocess.run(['google-chrome', '--version'],
                                          capture_output=True, text=True, timeout=5)
            logger.info(f"Chrome: {chrome_result.stdout.strip()}")

            # Check ChromeDriver
            driver_result = subprocess.run(['chromedriver', '--version'],
                                          capture_output=True, text=True, timeout=5)
            logger.info(f"ChromeDriver: {driver_result.stdout.strip()}")

            # Check Display
            display = os.getenv('DISPLAY', 'NOT SET')
            logger.info(f"DISPLAY environment: {display}")

            # Check Xvfb
            xvfb_result = subprocess.run(['ps', 'aux'],
                                        capture_output=True, text=True, timeout=5)
            if 'Xvfb' in xvfb_result.stdout:
                logger.info("Xvfb is running ✓")
            else:
                logger.warning("Xvfb not found in process list!")

            # Check directories
            logger.info(f"Download dir exists: {os.path.exists(self.config.DOWNLOAD_DIR)}")
            logger.info(f"Chrome data dir exists: {os.path.exists(self.config.CHROME_USER_DATA_DIR)}")

            return True
        except Exception as e:
            logger.error(f"Chrome installation check failed: {e}")
            return False
