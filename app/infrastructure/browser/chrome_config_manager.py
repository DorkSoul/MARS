"""Chrome Configuration Manager - Handles Chrome options and preferences"""

import os
import json
import logging
import glob
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)


class ChromeConfigManager:
    """Manages Chrome browser configuration, preferences, and session state"""

    def __init__(self, config):
        """
        Initialize the Chrome configuration manager

        Args:
            config: Application config object with CHROME_USER_DATA_DIR
        """
        self.config = config

    def create_chrome_options(self):
        """
        Create Chrome options with all necessary flags and preferences

        Returns:
            Options: Configured Chrome options object
        """
        chrome_options = Options()

        # Essential flags for Docker
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

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

        # Enable performance logging to capture network events
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        return chrome_options

    def reset_preferences(self):
        """
        Reset Chrome preferences to fix crash flags and session restore issues

        This fixes the "Chrome did not shut down correctly" message and
        prevents blank windows with highlighted URLs due to session restore.
        """
        try:
            prefs_path = os.path.join(self.config.CHROME_USER_DATA_DIR, 'Default', 'Preferences')
            if not os.path.exists(prefs_path):
                return

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
                logger.info("Resetting Chrome crash flag and session restore settings in Preferences")
                with open(prefs_path, 'w', encoding='utf-8') as f:
                    json.dump(prefs, f)

        except Exception as e:
            logger.warning(f"Could not reset Chrome preferences: {e}")

    def cleanup_lock_files(self):
        """
        Clean up Chrome lock files that may prevent startup

        This removes SingletonLock and lockfile entries that can cause
        "Chrome instance exited" errors when Chrome didn't shut down cleanly.
        """
        try:
            lock_files = glob.glob(
                os.path.join(self.config.CHROME_USER_DATA_DIR, '**/SingletonLock'),
                recursive=True
            )
            lock_files.extend(
                glob.glob(
                    os.path.join(self.config.CHROME_USER_DATA_DIR, '**/lockfile'),
                    recursive=True
                )
            )

            for lock_file in lock_files:
                try:
                    os.remove(lock_file)
                    logger.info(f"Removed lock file: {lock_file}")
                except Exception as e:
                    logger.warning(f"Could not remove {lock_file}: {e}")

        except Exception as e:
            logger.warning(f"Error during lock file cleanup: {e}")
