import os
import time
import json
import logging
import subprocess
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

download_bp = Blueprint('download', __name__, url_prefix='/api/downloads')

# Cache for file metadata to avoid repeated ffprobe calls
_metadata_cache = {}


def init_download_routes(download_service, download_dir):
    """Initialize download routes with services"""

    def get_file_metadata(filepath):
        """Extract metadata from a video file using ffprobe"""
        try:
            # Check cache first (use file modification time as cache key)
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
            return {'resolution': 'Unknown', 'duration': 0, 'framerate': ''}

    def get_file_thumbnail(filepath):
        """Extract thumbnail from a video file"""
        import base64
        import tempfile
        
        try:
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
            
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, 'rb') as f:
                    thumbnail = base64.b64encode(f.read()).decode('utf-8')
                os.unlink(tmp_path)
                return thumbnail
            
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None
            
        except Exception as e:
            logger.error(f"Error extracting thumbnail from {filepath}: {e}")
            return None

    @download_bp.route('/direct', methods=['POST'])
    def download_direct():
        """Direct download from stream URL"""
        try:
            data = request.json
            stream_url = data.get('url')

            if not stream_url:
                return jsonify({'error': 'No URL provided'}), 400

            # Generate filename
            timestamp = int(time.time())
            filename = data.get('filename', f"video_{timestamp}.mp4")

            # Start download
            browser_id, output_path = download_service.start_direct_download(
                f"direct_{timestamp}",
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
            if os.path.exists(download_dir):
                for filename in os.listdir(download_dir):
                    # Skip files that are currently being downloaded
                    if filename in active_filenames:
                        continue
                        
                    filepath = os.path.join(download_dir, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        
                        # Get metadata
                        metadata = get_file_metadata(filepath)
                        
                        # Get thumbnail
                        thumbnail = get_file_thumbnail(filepath)
                        
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
            
            filepath = os.path.join(download_dir, filename)
            exists = os.path.exists(filepath)
            
            return jsonify({'exists': exists, 'filename': filename})
        except Exception as e:
            logger.error(f"Check filename error: {e}")
            return jsonify({'exists': False, 'error': str(e)})

    @download_bp.route('/stop/<browser_id>', methods=['POST'])
    def stop_download(browser_id):
        """Stop an active download"""
        try:
            if download_service.stop_download(browser_id):
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
            filepath = os.path.join(download_dir, filename)
            
            # Security check: ensure the file is within download_dir
            real_path = os.path.realpath(filepath)
            real_download_dir = os.path.realpath(download_dir)
            
            if not real_path.startswith(real_download_dir):
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

    return download_bp
