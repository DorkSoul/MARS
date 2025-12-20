import os
import sys
import logging

class Config:
    """Application configuration"""

    def __init__(self):
        # Directories
        self.DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/app/downloads')
        self.CHROME_USER_DATA_DIR = os.getenv('CHROME_USER_DATA_DIR', '/app/chrome-data')

        # Timing
        self.AUTO_CLOSE_DELAY = int(os.getenv('AUTO_CLOSE_DELAY', '15'))

        # Schedules
        self.SCHEDULES_FILE = os.path.join(self.CHROME_USER_DATA_DIR, 'schedules.json')

        # Chrome paths
        self.CHROMEDRIVER_PATH = '/usr/local/bin/chromedriver'
        self.CHROMEDRIVER_LOG_PATH = '/app/logs/chromedriver.log'

        # Logging
        self.LOG_FILE_PATH = '/app/logs/flask.log'
        self.LOG_LEVEL = logging.INFO

    def setup_logging(self):
        """Configure logging for the application"""
        logging.basicConfig(
            level=self.LOG_LEVEL,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(self.LOG_FILE_PATH)
            ]
        )

        # Silence noisy third-party loggers
        logging.getLogger('selenium').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)  # Suppress "Connection pool is full" warnings
        logging.getLogger('websocket').setLevel(logging.ERROR)  # Suppress websocket noise
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

        return logging.getLogger(__name__)

    def check_directories(self):
        """Ensure required directories exist"""
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(self.CHROME_USER_DATA_DIR, exist_ok=True)

    def log_startup_info(self, logger):
        """Log startup information"""
        logger.info("=" * 80)
        logger.info("UNIVERSAL VIDEO DOWNLOADER STARTING")
        logger.info("=" * 80)
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"DISPLAY: {os.getenv('DISPLAY')}")
        logger.info(f"Download dir: {self.DOWNLOAD_DIR}")
        logger.info(f"Chrome data dir: {self.CHROME_USER_DATA_DIR}")
