"""Stream selection and download coordination logic"""

import time
import logging
import threading
from typing import List, Dict, Optional, Any, Callable

from app.utils import MetadataExtractor, ThumbnailGenerator

logger = logging.getLogger(__name__)


class StreamSelectionCoordinator:
    """
    Coordinates stream selection, metadata enrichment, and download initiation.

    This class manages the workflow from stream detection to download start:
    1. Presenting available streams for user selection
    2. Enriching stream metadata using ffprobe
    3. Generating thumbnails from stream URLs
    4. Managing selection state (awaiting user input)
    5. Coordinating download initiation with appropriate callbacks
    6. Generating filenames based on resolution and user preferences

    The coordinator acts as a bridge between stream detection (network layer)
    and download execution (download manager), handling all the intermediate
    steps of stream preparation and user interaction.
    """

    def __init__(self, config, filename: Optional[str] = None, output_format: str = 'mp4'):
        """
        Initialize the stream selection coordinator.

        Args:
            config: Application configuration object
            filename: Optional custom filename for downloads (without extension)
            output_format: Output file format/extension (mp4, mkv, mp3, etc.)
        """
        self.config = config
        self.filename = filename
        self.output_format = output_format

        # Selection state
        self.awaiting_resolution_selection = False
        self.available_resolutions = []
        self.selected_stream_url = None
        self.selected_stream_metadata = None

        # Thumbnail state
        self.thumbnail_data = None

        # Download callback
        self.download_callback = None
        self.download_started = False

    def set_download_callback(self, callback: Callable):
        """
        Set the callback function for initiating downloads.

        The callback will be invoked when a stream is ready to download,
        passing all necessary information to start the download process.

        Args:
            callback: Function(browser_id, stream_url, filename, resolution_name, metadata)
        """
        self.download_callback = callback

    def show_stream_selection(self, resolutions: List[Dict[str, Any]]):
        """
        Present multiple streams to the user for manual selection.

        This method:
        1. Sets the selection state to awaiting user input
        2. Stores available resolutions
        3. Enriches metadata and generates thumbnails for the first 5 streams
           in background threads to improve UI responsiveness

        Args:
            resolutions: List of stream dictionaries with resolution metadata
        """
        self.awaiting_resolution_selection = True
        self.available_resolutions = resolutions

        logger.info(f"Presenting {len(resolutions)} streams for user selection")

        # Enrich metadata and generate thumbnails in background (first 5 streams)
        # This improves perceived performance by not blocking on metadata extraction
        for res in resolutions[:5]:
            threading.Thread(
                target=self.enrich_stream_metadata,
                args=(res,),
                daemon=True
            ).start()

    def select_resolution(self, resolution_name: str) -> bool:
        """
        User has selected a specific resolution to download.

        This method:
        1. Finds the matching stream in available resolutions
        2. Initiates the download process
        3. Returns success/failure status

        Args:
            resolution_name: Name/identifier of the selected resolution

        Returns:
            True if resolution found and download started, False otherwise
        """
        if not self.awaiting_resolution_selection:
            logger.warning("Not awaiting resolution selection")
            return False

        # Find the selected stream
        selected_stream = None
        for res in self.available_resolutions:
            if res.get('name') == resolution_name:
                selected_stream = res
                break

        if not selected_stream:
            logger.error(f"Resolution '{resolution_name}' not found in available streams")
            return False

        logger.info(f"User selected resolution: {resolution_name}")

        # Clear selection state
        self.awaiting_resolution_selection = False

        # Start download with the selected stream
        self.start_download(selected_stream)
        return True

    def enrich_stream_metadata(self, stream_dict: Dict[str, Any]):
        """
        Enrich stream metadata and generate thumbnail.

        This method:
        1. Uses MetadataExtractor to fill in missing stream metadata via ffprobe
        2. Uses ThumbnailGenerator to create a thumbnail from the stream URL
        3. Handles all exceptions gracefully (metadata enrichment is best-effort)

        The stream_dict is modified in-place with enriched data.

        Args:
            stream_dict: Stream dictionary to enrich (modified in-place)
        """
        try:
            # Enrich metadata using ffprobe if fields are missing
            MetadataExtractor.enrich_stream_metadata(stream_dict)

            # Generate thumbnail from stream URL
            stream_url = stream_dict.get('url')
            if stream_url:
                thumbnail = ThumbnailGenerator.generate_stream_thumbnail(stream_url)
                if thumbnail:
                    stream_dict['thumbnail'] = thumbnail
                    logger.debug(f"Added thumbnail to stream: {stream_dict.get('name', 'unknown')}")
        except Exception as e:
            # Metadata enrichment is best-effort, don't fail the entire process
            logger.warning(f"Failed to enrich stream metadata: {e}")

    def start_download(self, stream: Dict[str, Any], browser_id: Optional[str] = None):
        """
        Initiate download for a selected stream.

        This method:
        1. Marks download as started
        2. Stores selected stream information
        3. Extracts thumbnail data if available
        4. Generates appropriate filename
        5. Invokes the download callback to trigger actual download

        Args:
            stream: Stream dictionary containing URL and metadata
            browser_id: Optional browser identifier (for multi-browser scenarios)
        """
        if self.download_started:
            logger.warning("Download already started, ignoring duplicate request")
            return

        self.download_started = True
        self.selected_stream_url = stream['url']
        self.selected_stream_metadata = stream

        resolution_name = stream.get('name', 'video')
        logger.info(f"Starting download for resolution: {resolution_name}")

        # Extract thumbnail data if available
        if 'thumbnail' in stream:
            thumbnail = stream['thumbnail']
            if thumbnail.startswith('data:image/'):
                # Strip the data URI prefix to get base64 data
                self.thumbnail_data = thumbnail.split(',', 1)[1]
            else:
                self.thumbnail_data = thumbnail

        # Generate filename
        filename = self._generate_filename(resolution_name)

        # Call download callback if set
        if self.download_callback:
            self.download_callback(
                browser_id,
                stream['url'],
                filename,
                resolution_name,
                stream
            )
        else:
            logger.warning("No download callback set, cannot start download")

    def start_download_with_url(
        self,
        stream_url: str,
        resolution_name: str,
        stream_metadata: Optional[Dict[str, Any]] = None,
        browser_id: Optional[str] = None
    ):
        """
        Initiate download with explicit URL and metadata.

        This is a convenience method for cases where you have a direct URL
        rather than a complete stream dictionary.

        Args:
            stream_url: Direct URL to the stream
            resolution_name: Name/identifier for this stream
            stream_metadata: Optional metadata dictionary
            browser_id: Optional browser identifier
        """
        # Construct a minimal stream dictionary
        stream = {
            'url': stream_url,
            'name': resolution_name,
            'bandwidth': stream_metadata.get('bandwidth', 0) if stream_metadata else 0,
            'resolution': stream_metadata.get('resolution', '') if stream_metadata else '',
            'framerate': stream_metadata.get('framerate', '') if stream_metadata else '',
            'codecs': stream_metadata.get('codecs', '') if stream_metadata else ''
        }

        # Copy thumbnail if present
        if stream_metadata and 'thumbnail' in stream_metadata:
            stream['thumbnail'] = stream_metadata['thumbnail']

        self.start_download(stream, browser_id)

    def capture_fallback_thumbnail(self, driver):
        """
        Capture a fallback thumbnail from the browser if stream thumbnail failed.

        This is typically called after navigation when the video player is loaded
        but before metadata enrichment could generate a thumbnail.

        Args:
            driver: Selenium WebDriver instance
        """
        if not self.thumbnail_data and driver:
            logger.info("Capturing fallback thumbnail from browser")
            self.thumbnail_data = ThumbnailGenerator.capture_screenshot(driver)

    def _generate_filename(self, resolution_name: str) -> str:
        """
        Generate an appropriate filename for the download.

        Filename generation logic:
        1. If custom filename provided:
           - Use as-is if it contains an extension
           - Append output_format extension if no extension present
        2. If no custom filename:
           - Generate: video_{resolution}_{timestamp}.{ext}

        Args:
            resolution_name: Resolution identifier to include in filename

        Returns:
            Complete filename with extension
        """
        ext = self.output_format

        if self.filename:
            # Check if filename already has an extension
            if '.' in self.filename:
                return self.filename
            else:
                return f"{self.filename}.{ext}"
        else:
            # Generate timestamp-based filename
            timestamp = int(time.time())
            # Sanitize resolution name for filename (remove special chars)
            safe_resolution = resolution_name.replace(' ', '_').replace('/', '_')
            return f"video_{safe_resolution}_{timestamp}.{ext}"

    def get_selection_state(self) -> Dict[str, Any]:
        """
        Get current selection state information.

        Returns a dictionary with:
        - awaiting_resolution_selection: Whether waiting for user input
        - available_resolutions: List of streams available for selection
        - selected_stream_metadata: Metadata of currently selected stream
        - thumbnail: Current thumbnail data
        - download_started: Whether download has been initiated

        Returns:
            Dictionary containing current state
        """
        return {
            'awaiting_resolution_selection': self.awaiting_resolution_selection,
            'available_resolutions': self.available_resolutions,
            'selected_stream_metadata': self.selected_stream_metadata,
            'thumbnail': self.thumbnail_data,
            'download_started': self.download_started
        }

    def reset(self):
        """
        Reset coordinator state for reuse.

        Clears all selection state and thumbnails, preparing the coordinator
        for a new stream detection/selection cycle.
        """
        self.awaiting_resolution_selection = False
        self.available_resolutions = []
        self.selected_stream_url = None
        self.selected_stream_metadata = None
        self.thumbnail_data = None
        self.download_started = False
        logger.debug("StreamSelectionCoordinator state reset")
