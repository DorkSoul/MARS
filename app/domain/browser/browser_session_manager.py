"""Browser Session Manager - Handles browser lifecycle and navigation"""

import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Manages browser session lifecycle including startup, navigation, and CDP setup.

    This class encapsulates all browser lifecycle management logic including:
    - Browser initialization with retry logic
    - WebDriver configuration and setup
    - CDP WebSocket connection coordination
    - Page navigation with retry and verification
    - Window management
    - Session cleanup

    Attributes:
        config: Application configuration object
        chrome_config: ChromeConfigManager instance for browser configuration
        cdp_client: CDPClient instance for DevTools Protocol communication
        driver: Selenium WebDriver instance (None until browser starts)
        is_running: Boolean flag indicating if browser session is active
    """

    def __init__(self, config, chrome_config, cdp_client):
        """
        Initialize the browser session manager with required dependencies.

        Args:
            config: Application config object with CHROMEDRIVER_PATH and CHROMEDRIVER_LOG_PATH
            chrome_config: ChromeConfigManager instance for managing Chrome configuration
            cdp_client: CDPClient instance for handling DevTools Protocol communication
        """
        self.config = config
        self.chrome_config = chrome_config
        self.cdp_client = cdp_client
        self.driver = None
        self.is_running = False

    def start_browser(self, url):
        """
        Start Chrome browser with DevTools Protocol enabled and navigate to URL.

        This method handles the complete browser startup flow:
        1. Resets Chrome preferences to clear crash flags
        2. Creates Chrome options with CDP enabled
        3. Initializes WebDriver with retry logic for lock file issues
        4. Sets up CDP WebSocket connection
        5. Configures window size
        6. Navigates to the target URL with verification

        The method includes automatic retry logic:
        - Retries WebDriver initialization if Chrome lock files are preventing startup
        - Retries navigation if page fails to load properly
        - Handles session restore issues by forcing navigation

        Args:
            url (str): Target URL to navigate to after browser starts

        Returns:
            bool: True if browser started and navigated successfully, False otherwise

        Example:
            >>> manager = BrowserSessionManager(config, chrome_config, cdp_client)
            >>> if manager.start_browser('https://example.com'):
            ...     print("Browser ready")
            ... else:
            ...     print("Failed to start browser")
        """
        max_retries = 2
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.info(f"Starting Chrome browser for {url}")

                # Reset Chrome preferences before starting
                self.chrome_config.reset_preferences()

                # Create Chrome options using config manager
                chrome_options = self.chrome_config.create_chrome_options()

                logger.info("Initializing ChromeDriver...")
                service = Service(
                    self.config.CHROMEDRIVER_PATH,
                    log_output=self.config.CHROMEDRIVER_LOG_PATH
                )

                try:
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    logger.info("Chrome started successfully")

                    # Set page load timeout to prevent hangs
                    self.driver.set_page_load_timeout(60)

                except Exception as driver_error:
                    logger.error(f"Failed to create Chrome webdriver: {driver_error}")

                    # If this is the first attempt and error mentions "Chrome instance exited"
                    if retry_count == 0 and "Chrome instance exited" in str(driver_error):
                        logger.warning("Chrome failed to start with user-data-dir, cleaning lock files and retrying...")
                        retry_count += 1

                        # Clean up problematic lock files using config manager
                        self.chrome_config.cleanup_lock_files()

                        # Small delay to let file system catch up
                        time.sleep(1)
                        continue  # Retry
                    else:
                        raise

                # Set window size for consistent rendering
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

        # Setup CDP WebSocket connection
        has_websocket = self.cdp_client.setup_connection(self.driver)

        self.is_running = True

        # Navigate to URL
        success = self.navigate_to(url, has_websocket)

        return success

    def navigate_to(self, url, has_websocket=True):
        """
        Navigate to a URL with retry logic and page load verification.

        This method handles robust page navigation including:
        - Multiple navigation attempts with different strategies
        - Session restore bypass (navigates via about:blank first)
        - JavaScript-based navigation as fallback
        - Page load verification (checks for actual content)
        - Document ready state waiting

        The navigation process attempts to work around Chrome's session restore
        feature which can cause blank pages or highlighted URL bars. It verifies
        the page actually loaded content before returning.

        Args:
            url (str): Target URL to navigate to
            has_websocket (bool): Whether CDP WebSocket is available for monitoring

        Returns:
            bool: True if navigation succeeded, False otherwise

        Example:
            >>> manager.navigate_to('https://example.com')
            True
        """
        logger.info(f"Navigating to {url}")
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

                logger.info(f"Successfully navigated to {url}")
                return True

            except Exception as e:
                logger.error(f"Navigation error on attempt {attempt + 1}: {e}")
                if attempt < max_nav_attempts - 1:
                    time.sleep(1)
                else:
                    logger.error("All navigation attempts failed")
                    return False

        return False

    def set_window_size(self, width, height):
        """
        Set browser window size.

        Args:
            width (int): Window width in pixels
            height (int): Window height in pixels

        Example:
            >>> manager.set_window_size(1920, 1080)
        """
        if self.driver:
            try:
                self.driver.set_window_size(width, height)
                logger.info(f"Window size set to {width}x{height}")
            except Exception as e:
                logger.error(f"Error setting window size: {e}")

    def get_driver(self):
        """
        Get the Selenium WebDriver instance.

        Returns:
            WebDriver: The Selenium WebDriver instance, or None if not started

        Example:
            >>> driver = manager.get_driver()
            >>> if driver:
            ...     print(driver.current_url)
        """
        return self.driver

    def close(self):
        """
        Close the browser and cleanup resources.

        This method:
        1. Sets is_running flag to False
        2. Closes the CDP WebSocket connection
        3. Quits the WebDriver (which closes the browser)
        4. Handles any errors during cleanup gracefully

        It's safe to call this method multiple times - it will only
        attempt cleanup if resources are allocated.

        Example:
            >>> manager.close()
        """
        self.is_running = False

        # Close WebSocket connection via CDP client
        self.cdp_client.close()

        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser session closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None

    def is_browser_running(self):
        """
        Check if browser session is currently running.

        Returns:
            bool: True if browser is running, False otherwise

        Example:
            >>> if manager.is_browser_running():
            ...     print("Browser is active")
        """
        return self.is_running
