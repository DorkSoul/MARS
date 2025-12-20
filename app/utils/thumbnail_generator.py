import os
import time
import base64
import logging
import subprocess
from PIL import Image
import io

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """Handles generation of thumbnails from video streams and files"""

    @staticmethod
    def generate_stream_thumbnail(stream_url):
        """Extract a single frame from a stream URL for thumbnail"""
        temp_file = None
        try:
            logger.debug(f"Generating thumbnail for stream: {stream_url[:100]}...")

            # Create temporary output file
            temp_file = f"/tmp/thumb_{int(time.time())}_{os.getpid()}.jpg"

            # Use ffmpeg to extract a frame at 2 seconds into the stream
            cmd = [
                'ffmpeg',
                '-loglevel', 'error',
                '-i', stream_url,
                '-ss', '00:00:02',  # Seek to 2 seconds
                '-vframes', '1',     # Extract 1 frame
                '-q:v', '2',         # High quality JPEG
                '-y',                # Overwrite
                temp_file
            ]

            logger.debug(f"Running ffmpeg command: {' '.join(cmd[:5])}...")

            # Run with timeout (15 seconds max)
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15
            )

            # Check if thumbnail was created
            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                # Read and encode as base64
                with open(temp_file, 'rb') as f:
                    thumbnail_data = base64.b64encode(f.read()).decode('utf-8')

                # Clean up temp file
                os.remove(temp_file)

                logger.debug(f"✓ Thumbnail generated successfully ({len(thumbnail_data)} bytes)")
                return f"data:image/jpeg;base64,{thumbnail_data}"
            else:
                if os.path.exists(temp_file):
                    logger.warning(f"Thumbnail file created but empty (size: {os.path.getsize(temp_file)})")
                else:
                    logger.warning("Thumbnail file was not created by ffmpeg")

                if process.stderr:
                    stderr_text = process.stderr.decode('utf-8', errors='ignore')
                    if stderr_text.strip():
                        logger.warning(f"FFmpeg stderr: {stderr_text[:200]}")

                return None

        except subprocess.TimeoutExpired:
            logger.warning("Thumbnail generation timed out after 15 seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"Thumbnail generation traceback: {traceback.format_exc()}")
            return None
        finally:
            # Clean up temp file if it exists
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug(f"Cleaned up temp thumbnail file: {temp_file}")
                except Exception as cleanup_error:
                    logger.debug(f"Failed to clean up temp file: {cleanup_error}")

    @staticmethod
    def extract_thumbnail_from_file(file_path, cache_dict, cache_key, cache_timeout=10, seek_time=2):
        """
        Extract a thumbnail from a partially downloaded video file.
        Returns base64 encoded image or None if extraction fails.
        Caches thumbnails for specified timeout to avoid excessive CPU usage.
        """
        try:
            # Check cache - only extract if more than cache_timeout seconds since last extraction
            current_time = time.time()
            if cache_key in cache_dict:
                cached = cache_dict[cache_key]
                if current_time - cached['timestamp'] < cache_timeout:
                    # Return cached thumbnail
                    return cached['thumbnail']

            # Check if file exists and has content
            if not os.path.exists(file_path):
                logger.debug(f"Thumbnail: file does not exist: {file_path}")
                return None

            file_size = os.path.getsize(file_path)
            if file_size < 50000:  # Less than 50KB - too small for thumbnail
                logger.debug(f"Thumbnail: file too small ({file_size} bytes): {file_path}")
                return None

            logger.debug(f"Extracting thumbnail from {file_path} ({file_size} bytes) at {seek_time}s")

            # Extract frame from beginning of downloaded content
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output
                '-loglevel', 'error',  # Show errors only
                '-ss', str(seek_time),  # Seek to custom time
                '-i', file_path,
                '-frames:v', '1',  # Extract 1 frame
                '-q:v', '2',  # Quality
                '-f', 'image2pipe',  # Output to pipe
                '-vcodec', 'png',
                'pipe:1'
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=5)

            if result.returncode == 0 and result.stdout:
                # Convert to base64
                thumbnail_base64 = base64.b64encode(result.stdout).decode('utf-8')

                # Cache the thumbnail
                cache_dict[cache_key] = {
                    'thumbnail': thumbnail_base64,
                    'timestamp': current_time
                }

                logger.debug(f"✓ Thumbnail extracted successfully ({len(thumbnail_base64)} bytes base64)")
                return thumbnail_base64

            # Thumbnail extraction failures are expected for partial files - use debug level
            logger.debug(f"Thumbnail extraction failed: ffmpeg returned {result.returncode}")
            if result.stderr:
                stderr_msg = result.stderr.decode('utf-8')[:500]
                # Only log if it's not a common partial file error
                if 'partial file' not in stderr_msg.lower() and 'invalid nal unit' not in stderr_msg.lower():
                    logger.debug(f"ffmpeg stderr: {stderr_msg}")
            return None

        except subprocess.TimeoutExpired:
            logger.debug(f"Thumbnail extraction timeout for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Thumbnail extraction error: {e}")
            return None

    @staticmethod
    def capture_screenshot(driver, width=400, height=300):
        """Capture screenshot from Selenium driver and return as base64"""
        try:
            if driver:
                screenshot = driver.get_screenshot_as_png()
                image = Image.open(io.BytesIO(screenshot))

                # Resize to thumbnail
                image.thumbnail((width, height))

                # Convert to base64
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                thumbnail_data = base64.b64encode(buffered.getvalue()).decode('utf-8')

                logger.debug("Thumbnail captured successfully")
                return thumbnail_data
        except Exception as e:
            logger.error(f"Failed to capture thumbnail: {e}")
            return None
