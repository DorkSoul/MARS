"""Browser Registry component for managing browser instances lifecycle"""

import logging
import threading

logger = logging.getLogger(__name__)


class BrowserRegistry:
    """
    Manages registry of active browser instances.

    Provides thread-safe operations for registering, retrieving, and managing
    browser detector instances. Enforces singleton pattern by clearing all
    browsers before registering a new one.
    """

    def __init__(self):
        """Initialize browser registry with empty dict and lock"""
        self._active_browsers = {}
        self._lock = threading.Lock()

    def register(self, browser_id, detector, enforce_singleton=True):
        """
        Register a new browser detector instance.

        Args:
            browser_id: Unique identifier for the browser
            detector: StreamDetector instance to register
            enforce_singleton: If True, close all existing browsers first

        Returns:
            bool: True if registration successful
        """
        with self._lock:
            if enforce_singleton and self._active_browsers:
                logger.info("Enforcing singleton: closing existing browsers before registration")
                self._close_all_internal()

            self._active_browsers[browser_id] = detector
            logger.debug(f"Registered browser {browser_id}")
            return True

    def unregister(self, browser_id):
        """
        Unregister and close a specific browser instance.

        Args:
            browser_id: ID of browser to unregister

        Returns:
            bool: True if browser was found and unregistered
        """
        with self._lock:
            if browser_id in self._active_browsers:
                detector = self._active_browsers[browser_id]
                try:
                    detector.close()
                    logger.debug(f"Closed browser {browser_id}")
                except Exception as e:
                    logger.error(f"Error closing browser {browser_id}: {e}")

                del self._active_browsers[browser_id]
                return True
            return False

    def get(self, browser_id):
        """
        Get a browser detector instance by ID.

        Args:
            browser_id: ID of browser to retrieve

        Returns:
            StreamDetector instance or None if not found
        """
        with self._lock:
            return self._active_browsers.get(browser_id)

    def get_all(self):
        """
        Get all active browser IDs.

        Returns:
            list: List of active browser IDs
        """
        with self._lock:
            return list(self._active_browsers.keys())

    def has(self, browser_id):
        """
        Check if a browser is registered.

        Args:
            browser_id: ID to check

        Returns:
            bool: True if browser exists in registry
        """
        with self._lock:
            return browser_id in self._active_browsers

    def clear_all(self):
        """
        Close and unregister all browsers.

        Returns:
            list: List of browser IDs that were closed
        """
        with self._lock:
            return self._close_all_internal()

    def _close_all_internal(self):
        """
        Internal method to close all browsers (must be called within lock).

        Returns:
            list: List of browser IDs that were closed
        """
        closed_ids = []
        browsers_to_close = list(self._active_browsers.keys())

        for browser_id in browsers_to_close:
            detector = self._active_browsers[browser_id]
            try:
                detector.close()
                closed_ids.append(browser_id)
                logger.debug(f"Closed browser {browser_id}")
            except Exception as e:
                logger.error(f"Error closing browser {browser_id}: {e}")

        self._active_browsers.clear()
        return closed_ids

    def __len__(self):
        """Return number of active browsers"""
        with self._lock:
            return len(self._active_browsers)

    def __contains__(self, browser_id):
        """Support 'in' operator"""
        return self.has(browser_id)
