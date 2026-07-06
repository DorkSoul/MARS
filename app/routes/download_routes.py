import os
import time
import json
import logging
import subprocess
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

download_bp = Blueprint('download', __name__, url_prefix='/api/downloads')

# Caches for file metadata/thumbnails to avoid repeated ffprobe/ffmpeg calls.
# Keyed by "path:mtime" so entries invalidate when a file changes; stale keys
# are evicted on each /list request.
_metadata_cache = {}
_thumbnail_cache = {}


def init_download_routes(download_service, download_dir, scheduler=None):
    """Initialize download routes with services"""

    def resolve_in_download_dir(filename):
        """Resolve filename inside download_dir; return None if it escapes."""
        filepath = os.path.realpath(os.path.join(download_dir, filename))
        base = os.path.realpath(download_dir)
        if filepath == base or os.path.commonpath([filepath, base]) != base:
            return None
        return filepath

    def get_file_metadata(filepath, cache_key=None):
        """Extract metadata from a video file using ffprobe (cached by path+mtime).

        Failures (including ffprobe timeouts) are cached so a broken file
        doesn't respawn ffprobe on every poll.
        """
        try:
            # Check cache first (file modification time as cache key)
            if cache_key is None:
                stat = os.stat(filepath)
                cache_key = f"{filepath}:{stat.st_mtime}"

            if cache_key in _metadata_cache:
                return _metadata_cache[cache_key]

            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-show_format',
                filepath
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                text=True
            )
            
            metadata = {
                'resolution': 'Unknown',
                'duration': 0,
                'framerate': ''
            }
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                
                # Get duration from format
                format_info = data.get('format', {})
                duration_str = format_info.get('duration', '0')
                try:
                    metadata['duration'] = int(float(duration_str))
                except:
                    pass
                
                # Find video stream
                video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
                if video_stream:
                    width = video_stream.get('width')
                    height = video_stream.get('height')
                    if width and height:
                        metadata['resolution'] = f"{width}x{height}"
                    
                    fps_str = video_stream.get('r_frame_rate', '')
                    if fps_str and '/' in fps_str:
                        try:
                            num, denom = fps_str.split('/')
                            fps = float(num) / float(denom)
                            metadata['framerate'] = f"{fps:.0f}fps"
                        except:
                            pass
            
            # Cache the result
            _metadata_cache[cache_key] = metadata
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata from {filepath}: {e}")
            fallback = {'resolution': 'Unknown', 'duration': 0, 'framerate': ''}
            if cache_key:
                _metadata_cache[cache_key] = fallback
            return fallback

    def get_file_thumbnail(filepath, cache_key=None):
        """Extract thumbnail from a video file (cached by path+mtime).

        Failures are cached too — including ffmpeg timeouts — so audio-only
        or corrupt files don't respawn FFmpeg on every poll.
        """
        import base64
        import tempfile

        tmp_path = None
        try:
            if cache_key is None:
                stat = os.stat(filepath)
                cache_key = f"{filepath}:{stat.st_mtime}"

            if cache_key in _thumbnail_cache:
                return _thumbnail_cache[cache_key]

            # Create temp file for thumbnail
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name

            cmd = [
                'ffmpeg',
                '-i', filepath,
                '-ss', '5',  # Seek to 5 seconds
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                '-y',
                tmp_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )

            thumbnail = None
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, 'rb') as f:
                    thumbnail = base64.b64encode(f.read()).decode('utf-8')

            _thumbnail_cache[cache_key] = thumbnail
            return thumbnail

        except Exception as e:
            logger.error(f"Error extracting thumbnail from {filepath}: {e}")
            if cache_key:
                _thumbnail_cache[cache_key] = None
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @download_bp.route('/direct', methods=['POST'])
    def download_direct():
        """Direct download from stream URL"""
        try:
            data = request.json
            stream_url = data.get('url')

            if not stream_url:
                return jsonify({'error': 'No URL provided'}), 400

            # Generate filename in format: HH-MM-SS-DDD-MMM.ext or name-HH-MM-SS-DDD-MMM.ext
            # Example: 14-30-45-Mon-Jan.mp4 or myName-14-30-45-Mon-Jan.mp4
            timestamp = int(time.time())  # Keep for browser_id uniqueness
            timestamp_str = datetime.now().strftime("%H-%M-%S-%a-%b")
            default_filename = f"{timestamp_str}.mp4"
            filename = data.get('filename', default_filename)

            browser_id = f"direct_{timestamp}"

            # Block scheduled checks before starting the download
            # (pause_all_for_manual also raises the manual-active flag)
            if scheduler:
                scheduler.pause_all_for_manual(browser_id)

            # Start download
            _, output_path = download_service.start_direct_download(
                browser_id,
                stream_url,
                filename
            )

            return jsonify({
                'success': True,
                'browser_id': browser_id,
                'message': 'Download started',
                'output_path': output_path
            })

        except Exception as e:
            logger.error(f"Direct download error: {e}")
            return jsonify({'error': str(e)}), 500

    @download_bp.route('/list', methods=['GET'])
    def list_downloads():
        """List all downloads with metadata"""
        try:
            downloads = []
            
            # Get list of filenames currently being downloaded
            active_downloads = download_service.get_active_downloads()
            active_filenames = {d.get('filename', '') for d in active_downloads if d.get('is_running', False)}

            # List completed downloads
            live_cache_keys = set()
            if os.path.exists(download_dir):
                for filename in os.listdir(download_dir):
                    # Skip files that are currently being downloaded
                    if filename in active_filenames:
                        continue

                    filepath = os.path.join(download_dir, filename)
                    if os.path.isfile(filepath):
                        # Stat once and share the cache key with both getters,
                        # so a file changing mid-request can't get cached
                        # under a key this request's eviction pass removes
                        stat = os.stat(filepath)
                        cache_key = f"{filepath}:{stat.st_mtime}"
                        live_cache_keys.add(cache_key)

                        metadata = get_file_metadata(filepath, cache_key)
                        thumbnail = get_file_thumbnail(filepath, cache_key)

                        downloads.append({
                            'filename': filename,
                            'size': stat.st_size,
                            'created': stat.st_ctime,
                            'path': filepath,
                            'resolution': metadata.get('resolution', 'Unknown'),
                            'duration': metadata.get('duration', 0),
                            'framerate': metadata.get('framerate', ''),
                            'thumbnail': thumbnail
                        })

            # Evict cache entries for files that were deleted or changed.
            # pop() (not del) — concurrent /list requests may race on the
            # same stale key
            for cache in (_metadata_cache, _thumbnail_cache):
                for key in list(cache.keys()):
                    if key not in live_cache_keys:
                        cache.pop(key, None)

            # Sort by creation time (newest first)
            downloads.sort(key=lambda x: x['created'], reverse=True)

            return jsonify({'downloads': downloads})

        except Exception as e:
            logger.error(f"List downloads error: {e}")
            return jsonify({'error': str(e)}), 500

    @download_bp.route('/active', methods=['GET'])
    def active_downloads():
        """Get active downloads with progress"""
        try:
            active = download_service.get_active_downloads()
            return jsonify({'active_downloads': active})

        except Exception as e:
            logger.error(f"Active downloads error: {e}")
            return jsonify({'error': str(e)}), 500

    @download_bp.route('/check-filename', methods=['GET'])
    def check_filename():
        """Check if a filename already exists in the download directory"""
        try:
            filename = request.args.get('filename', '')
            if not filename:
                return jsonify({'exists': False})

            filepath = resolve_in_download_dir(filename)
            if filepath is None:
                return jsonify({'exists': False, 'error': 'Invalid file path'}), 400

            exists = os.path.exists(filepath)

            return jsonify({'exists': exists, 'filename': filename})
        except Exception as e:
            logger.error(f"Check filename error: {e}")
            return jsonify({'exists': False, 'error': str(e)})

    @download_bp.route('/stop/<browser_id>', methods=['POST'])
    def stop_download(browser_id):
        """Stop an active download"""
        try:
            stopped = download_service.stop_download(browser_id)

            # Release this id's manual session (ownership-checked no-op for
            # ids that never registered, e.g. sched_ or stale ids), so
            # schedules can't get stuck auto-paused behind a stale session
            if scheduler:
                scheduler.resume_after_manual(browser_id)

            if stopped:
                return jsonify({'success': True, 'message': 'Download stopped'})
            else:
                return jsonify({'error': 'Download not found'}), 404

        except Exception as e:
            logger.error(f"Stop download error: {e}")
            return jsonify({'error': str(e)}), 500

    @download_bp.route('/delete/<path:filename>', methods=['DELETE'])
    def delete_download(filename):
        """Delete a completed download"""
        try:
            # Security check: ensure the file is within download_dir
            filepath = resolve_in_download_dir(filename)
            if filepath is None:
                return jsonify({'error': 'Invalid file path'}), 400

            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted file: {filepath}")
                return jsonify({'success': True, 'message': 'File deleted'})
            else:
                return jsonify({'error': 'File not found'}), 404

        except Exception as e:
            logger.error(f"Delete download error: {e}")
            return jsonify({'error': str(e)}), 500

    @download_bp.route('/history', methods=['GET'])
    def download_history():
        """Return the persisted download history log."""
        try:
            history = download_service.get_history()
            return jsonify({'history': history})
        except Exception as e:
            logger.error(f"History error: {e}")
            return jsonify({'error': str(e)}), 500

    return download_bp
