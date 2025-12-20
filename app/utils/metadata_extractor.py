import json
import logging
import subprocess

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Handles extraction of metadata from video streams"""

    @staticmethod
    def extract_stream_metadata_with_ffprobe(stream_url, timeout=8):
        """Extract metadata from stream using ffprobe"""
        try:
            logger.info(f"Extracting metadata with ffprobe for: {stream_url[:100]}...")

            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-show_format',
                stream_url
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
            )

            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)

                metadata = {
                    'resolution': '',
                    'framerate': '',
                    'codecs': ''
                }

                # Find video stream
                video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
                if video_stream:
                    # Extract resolution
                    width = video_stream.get('width')
                    height = video_stream.get('height')
                    if width and height:
                        metadata['resolution'] = f"{width}x{height}"

                    # Extract framerate
                    fps_str = video_stream.get('r_frame_rate', '')
                    if fps_str and '/' in fps_str:
                        try:
                            num, denom = fps_str.split('/')
                            fps = float(num) / float(denom)
                            metadata['framerate'] = f"{fps:.3f}"
                        except:
                            pass

                    # Extract codec
                    codec_name = video_stream.get('codec_name', '')
                    if codec_name:
                        metadata['codecs'] = codec_name

                logger.info(f"Extracted metadata: {metadata}")
                return metadata
            else:
                logger.warning(f"ffprobe failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Failed to extract metadata with ffprobe: {e}")
            return None

    @staticmethod
    def enrich_stream_metadata(stream_dict):
        """Enrich stream metadata using ffprobe if HLS attributes are missing"""
        needs_enrichment = (
            not stream_dict.get('resolution') or
            not stream_dict.get('framerate') or
            not stream_dict.get('codecs')
        )

        if needs_enrichment:
            missing_fields = []
            if not stream_dict.get('resolution'):
                missing_fields.append('resolution')
            if not stream_dict.get('framerate'):
                missing_fields.append('framerate')
            if not stream_dict.get('codecs'):
                missing_fields.append('codecs')

            logger.info(f"Stream metadata incomplete (missing: {', '.join(missing_fields)}), attempting to enrich with ffprobe: {stream_dict.get('name', 'unknown')}")
            metadata = MetadataExtractor.extract_stream_metadata_with_ffprobe(stream_dict['url'])

            if metadata:
                enriched = []
                # Fill in missing fields
                if not stream_dict.get('resolution') and metadata.get('resolution'):
                    stream_dict['resolution'] = metadata['resolution']
                    enriched.append(f"resolution={metadata['resolution']}")

                if not stream_dict.get('framerate') and metadata.get('framerate'):
                    stream_dict['framerate'] = metadata['framerate']
                    enriched.append(f"framerate={metadata['framerate']}")

                if not stream_dict.get('codecs') and metadata.get('codecs'):
                    stream_dict['codecs'] = metadata['codecs']
                    enriched.append(f"codecs={metadata['codecs']}")

                if enriched:
                    logger.info(f"  ✓ Enriched with: {', '.join(enriched)}")
                else:
                    logger.warning("  → ffprobe ran but couldn't extract any missing metadata")
            else:
                logger.warning("  → ffprobe enrichment failed, metadata will remain incomplete")
        else:
            logger.debug(f"Stream metadata already complete for: {stream_dict.get('name', 'unknown')}")

        return stream_dict
