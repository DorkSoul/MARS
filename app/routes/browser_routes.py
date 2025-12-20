import time
import logging
from flask import Blueprint, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import subprocess

logger = logging.getLogger(__name__)

browser_bp = Blueprint('browser', __name__, url_prefix='/api/browser')


def init_browser_routes(browser_service, download_service, config):
    """Initialize browser routes with services"""

    @browser_bp.route('/start', methods=['POST'])
    def start_browser():
        """Start browser for stream detection"""
        try:
            data = request.json
            url = data.get('url')
            resolution = data.get('resolution', '1080p')
            framerate = data.get('framerate', 'any')
            auto_download = data.get('auto_download', False)
            filename = data.get('filename', None)
            output_format = data.get('format', 'mp4')

            if not url:
                return jsonify({'error': 'No URL provided'}), 400

            logger.info(f"Starting browser with resolution: {resolution}, framerate: {framerate}")

            # Generate browser ID
            browser_id = f"browser_{int(time.time())}"

            # Start browser
            success, detector = browser_service.start_browser(
                url, browser_id, resolution, framerate, auto_download, filename, output_format
            )

            if success:
                return jsonify({
                    'success': True,
                    'browser_id': browser_id,
                    'message': 'Browser started',
                    'vnc_url': f'/vnc'
                })
            else:
                return jsonify({'error': 'Failed to start browser'}), 500

        except Exception as e:
            logger.error(f"Browser start error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/status/<browser_id>', methods=['GET'])
    def browser_status(browser_id):
        """Get browser or direct download status"""
        try:
            # Check browser status
            status = browser_service.get_browser_status(browser_id)

            if status:
                # Add download info if available
                download_info = download_service.get_download_status(browser_id)
                if download_info:
                    status['download'] = download_info
                return jsonify(status)

            # Check direct download status
            if browser_id in download_service.direct_download_status:
                status = download_service.direct_download_status[browser_id]
                download_info = download_service.get_download_status(browser_id)
                if download_info:
                    status['download'] = download_info
                return jsonify(status)

            return jsonify({'error': 'Browser not found'}), 404

        except Exception as e:
            logger.error(f"Status check error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/close/<browser_id>', methods=['POST'])
    def close_browser(browser_id):
        """Close browser manually"""
        try:
            if browser_service.close_browser(browser_id):
                return jsonify({'success': True, 'message': 'Browser closed'})
            else:
                return jsonify({'error': 'Browser not found'}), 404

        except Exception as e:
            logger.error(f"Browser close error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/select-resolution', methods=['POST'])
    def select_resolution():
        """User manually selected a resolution"""
        try:
            data = request.json
            browser_id = data.get('browser_id')
            stream = data.get('stream')

            if not all([browser_id, stream]):
                return jsonify({'error': 'Missing required parameters'}), 400

            success, message = browser_service.select_resolution(browser_id, stream)

            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'error': message}), 404

        except Exception as e:
            logger.error(f"Resolution selection error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/select-stream', methods=['POST'])
    def select_stream():
        """User manually selected a stream from the modal"""
        try:
            data = request.json
            browser_id = data.get('browser_id')
            stream_url = data.get('stream_url')

            if not browser_id or not stream_url:
                return jsonify({'error': 'Missing required parameters'}), 400

            success, message = browser_service.select_stream(browser_id, stream_url)

            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'error': message}), 404

        except Exception as e:
            logger.error(f"Stream selection error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/clear-cookies', methods=['POST'])
    def clear_cookies():
        """Clear Chrome cookies and profile data"""
        try:
            success, message = browser_service.clear_cookies()

            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'error': message}), 500

        except Exception as e:
            logger.error(f"Clear cookies error: {e}")
            return jsonify({'error': str(e)}), 500

    @browser_bp.route('/test/chrome', methods=['GET'])
    def test_chrome():
        """Test endpoint to diagnose Chrome issues"""
        try:
            logger.info("=" * 80)
            logger.info("CHROME TEST ENDPOINT CALLED")
            logger.info("=" * 80)

            results = {}

            # Test Chrome binary
            try:
                chrome_result = subprocess.run(['google-chrome', '--version'],
                                              capture_output=True, text=True, timeout=5)
                results['chrome_version'] = chrome_result.stdout.strip()
                results['chrome_available'] = True
            except Exception as e:
                results['chrome_available'] = False
                results['chrome_error'] = str(e)

            # Test ChromeDriver
            try:
                driver_result = subprocess.run(['chromedriver', '--version'],
                                              capture_output=True, text=True, timeout=5)
                results['chromedriver_version'] = driver_result.stdout.strip()
                results['chromedriver_available'] = True
            except Exception as e:
                results['chromedriver_available'] = False
                results['chromedriver_error'] = str(e)

            # Test minimal Chrome
            try:
                options = Options()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--headless=new')

                service = Service(config.CHROMEDRIVER_PATH)
                test_driver = webdriver.Chrome(service=service, options=options)
                test_driver.get('about:blank')

                results['chrome_test'] = 'SUCCESS'
                test_driver.quit()

            except Exception as e:
                results['chrome_test'] = 'FAILED'
                results['chrome_test_error'] = str(e)

            return jsonify(results)

        except Exception as e:
            logger.error(f"Test endpoint error: {e}")
            return jsonify({'error': str(e)}), 500

    return browser_bp
