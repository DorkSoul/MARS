"""
Stream discovery and processing service.

This service handles the discovery and processing of detected video streams,
including master playlist parsing, stream matching, and coordination with
download and selection components.
"""

import logging
import threading
from typing import Dict, List, Optional, Callable, Any

from app.utils import PlaylistParser, MetadataExtractor, ThumbnailGenerator
from app.domain.stream import StreamMatcher

logger = logging.getLogger(__name__)


class StreamDiscoveryService:
    """
    Domain service for handling stream discovery and processing.

    This service coordinates the processing of detected streams, including:
    - Identifying master playlists vs single streams
    - Parsing master playlists to extract available resolutions
    - Matching streams based on resolution/framerate preferences
    - Enriching stream metadata with additional information
    - Coordinating with callbacks for download triggers and UI selection

    The service uses a callback pattern to decouple from infrastructure
    concerns like download initiation and UI interactions.
    """

    def __init__(
        self,
        stream_matcher: StreamMatcher,
        auto_download: bool = False,
        download_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        selection_callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        """
        Initialize the stream discovery service.

        Args:
            stream_matcher: StreamMatcher instance for finding best matching streams
            auto_download: If True, automatically start download for matched streams
            download_callback: Callback function to trigger download with a stream
                             Signature: callback(stream_dict) -> None
            selection_callback: Callback function to show stream selection UI
                              Signature: callback(list_of_streams) -> None
        """
        self.stream_matcher = stream_matcher
        self.auto_download = auto_download
        self.download_callback = download_callback
        self.selection_callback = selection_callback

    def handle_detected_stream(self, stream_info: Dict[str, Any]) -> None:
        """
        Handle a detected stream - determine type and process accordingly.

        This is the main entry point for stream processing. It determines
        whether the stream is a master playlist or a single stream and
        delegates to the appropriate processing method.

        Args:
            stream_info: Dictionary containing stream metadata:
                - url: The stream URL
                - type: Stream type (HLS, DASH, MP4, etc.)
                - mime_type: MIME type of the stream
                - timestamp: Detection timestamp
        """
        stream_url = stream_info['url']

        if '.m3u8' in stream_url.lower():
            content = PlaylistParser.fetch_master_playlist(stream_url)

            if content and '#EXT-X-STREAM-INF:' in content:
                self.process_master_playlist(stream_url, content)
            else:
                self.process_single_stream(stream_url, stream_info)
        else:
            self.process_single_stream(stream_url, stream_info)

    def process_master_playlist(self, stream_url: str, content: str) -> None:
        """
        Process a master playlist containing multiple resolution variants.

        Parses the master playlist to extract available resolutions, then either:
        - Auto-downloads the best matching stream (if auto_download is enabled)
        - Shows stream selection UI (if auto_download is disabled or no match found)

        Args:
            stream_url: URL of the master playlist
            content: Raw content of the master playlist
        """
        resolutions = PlaylistParser.parse_master_playlist(content)

        if resolutions:
            if self.auto_download:
                matched_stream = self.stream_matcher.match_stream(resolutions)

                if matched_stream:
                    logger.info(f"Matched stream: {matched_stream['name']}")
                    self._enrich_and_add_thumbnail(matched_stream)
                    self._trigger_download(matched_stream)
                else:
                    self._show_stream_selection(resolutions)
            else:
                self._show_stream_selection(resolutions)
        else:
            self._show_unparsed_stream(stream_url)

    def process_single_stream(self, stream_url: str, stream_info: Dict[str, Any]) -> None:
        """
        Process a single stream (not a master playlist).

        Creates a stream entry for the single stream, then either:
        - Auto-downloads it (if auto_download is enabled)
        - Shows it in selection UI (if auto_download is disabled)

        Args:
            stream_url: URL of the stream
            stream_info: Dictionary containing stream metadata (type, mime_type, etc.)
        """
        stream_entry = {
            'url': stream_url,
            'bandwidth': 0,
            'resolution': '',
            'framerate': '',
            'codecs': '',
            'name': stream_info['type']
        }

        if self.auto_download:
            self._enrich_and_add_thumbnail(stream_entry)
            self._trigger_download(stream_entry)
        else:
            self._show_stream_selection([stream_entry])

    def _show_stream_selection(self, resolutions: List[Dict[str, Any]]) -> None:
        """
        Show streams for manual selection via callback.

        Enriches metadata and generates thumbnails in background for the first
        5 streams to improve user experience, then triggers the selection callback.

        Args:
            resolutions: List of stream dictionaries to show for selection
        """
        # Enrich metadata and generate thumbnails in background (first 5 streams)
        for res in resolutions[:5]:
            threading.Thread(
                target=self._enrich_and_add_thumbnail,
                args=(res,),
                daemon=True
            ).start()

        # Trigger selection callback
        if self.selection_callback:
            self.selection_callback(resolutions)

    def _show_unparsed_stream(self, stream_url: str) -> None:
        """
        Handle master playlist that couldn't be parsed.

        Creates a generic stream entry for the unparsed master playlist
        and shows it for selection. Enriches metadata in background.

        Args:
            stream_url: URL of the unparsed master playlist
        """
        logger.warning("Could not parse resolutions from master playlist")

        stream_entry = {
            'url': stream_url,
            'bandwidth': 0,
            'resolution': '',
            'framerate': '',
            'codecs': '',
            'name': 'Master Playlist (unparsed)'
        }

        # Enrich in background
        threading.Thread(
            target=self._enrich_and_add_thumbnail,
            args=(stream_entry,),
            daemon=True
        ).start()

        # Trigger selection callback
        if self.selection_callback:
            self.selection_callback([stream_entry])

    def _enrich_and_add_thumbnail(self, stream_dict: Dict[str, Any]) -> None:
        """
        Enrich stream metadata and add thumbnail.

        Attempts to extract additional metadata from the stream and generate
        a thumbnail preview. Failures are silently ignored to avoid blocking
        the main stream processing flow.

        Args:
            stream_dict: Stream dictionary to enrich (modified in-place)
        """
        try:
            # Enrich metadata
            MetadataExtractor.enrich_stream_metadata(stream_dict)

            # Add thumbnail
            stream_url = stream_dict.get('url')
            if stream_url:
                thumbnail = ThumbnailGenerator.generate_stream_thumbnail(stream_url)
                if thumbnail:
                    stream_dict['thumbnail'] = thumbnail
        except Exception:
            # Silently ignore enrichment failures
            pass

    def _trigger_download(self, stream: Dict[str, Any]) -> None:
        """
        Trigger download callback with the selected stream.

        Args:
            stream: Stream dictionary containing url, name, and metadata
        """
        if self.download_callback:
            self.download_callback(stream)
