"""
FFmpeg Strategy Pattern Implementation

This module implements the Strategy pattern for generating FFmpeg commands
based on the output format (audio vs video).
"""

import os
from abc import ABC, abstractmethod
from typing import List


class FFmpegStrategy(ABC):
    """Abstract base class for FFmpeg command generation strategies."""

    @abstractmethod
    def build_command(self, stream_url: str, output_path: str) -> List[str]:
        """
        Build FFmpeg command for the specific format.

        Args:
            stream_url: The URL of the stream to download
            output_path: The path where the output file will be saved

        Returns:
            List of command arguments for subprocess.Popen
        """
        pass


class AudioStrategy(FFmpegStrategy):
    """
    Strategy for generating FFmpeg commands for audio-only formats.

    Supports: mp3, aac, m4a, flac, wav, ogg, opus, wma
    """

    AUDIO_FORMATS = ['mp3', 'aac', 'm4a', 'flac', 'wav', 'ogg', 'opus', 'wma']

    def build_command(self, stream_url: str, output_path: str) -> List[str]:
        """
        Build FFmpeg command for audio extraction and encoding.

        Args:
            stream_url: The URL of the stream to download
            output_path: The path where the output file will be saved

        Returns:
            List of FFmpeg command arguments with audio-specific encoding options
        """
        # Get file extension
        ext = os.path.splitext(output_path)[1].lower().lstrip('.')

        # Base command for audio extraction
        cmd = [
            'ffmpeg',
            '-loglevel', 'error',  # Only show errors
            '-i', stream_url,
            '-vn',  # No video
        ]

        # Format-specific encoding options
        if ext == 'mp3':
            cmd.extend(['-c:a', 'libmp3lame', '-q:a', '2'])
        elif ext == 'aac':
            cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        elif ext == 'm4a':
            cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        elif ext == 'flac':
            cmd.extend(['-c:a', 'flac'])
        elif ext == 'wav':
            cmd.extend(['-c:a', 'pcm_s16le'])
        elif ext == 'ogg':
            cmd.extend(['-c:a', 'libvorbis', '-q:a', '6'])
        elif ext == 'opus':
            cmd.extend(['-c:a', 'libopus', '-b:a', '128k'])
        elif ext == 'wma':
            cmd.extend(['-c:a', 'wmav2', '-b:a', '192k'])

        # Add output path with overwrite flag
        cmd.extend(['-y', output_path])

        return cmd


class VideoStrategy(FFmpegStrategy):
    """
    Strategy for generating FFmpeg commands for video formats.

    Supports: mp4, mkv, webm, ts, flv, wmv, avi, and other video formats
    Uses stream copy where possible for optimal performance.
    """

    def build_command(self, stream_url: str, output_path: str) -> List[str]:
        """
        Build FFmpeg command for video downloading.

        Args:
            stream_url: The URL of the stream to download
            output_path: The path where the output file will be saved

        Returns:
            List of FFmpeg command arguments with video-specific options
        """
        # Get file extension
        ext = os.path.splitext(output_path)[1].lower().lstrip('.')

        # Base command for video
        cmd = [
            'ffmpeg',
            '-loglevel', 'error',  # Only show errors
            '-i', stream_url,
        ]

        # Format-specific options
        if ext in ['mp4', 'm4v', 'mov']:
            cmd.extend([
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                '-movflags', '+frag_keyframe+empty_moov',
            ])
        elif ext == 'mkv':
            cmd.extend(['-c', 'copy'])
        elif ext == 'webm':
            # WebM may need re-encoding if source isn't VP8/VP9
            cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])
        elif ext == 'ts':
            cmd.extend(['-c', 'copy', '-bsf:v', 'h264_mp4toannexb'])
        elif ext == 'flv':
            cmd.extend(['-c', 'copy'])
        elif ext == 'wmv':
            cmd.extend(['-c:v', 'wmv2', '-c:a', 'wmav2'])
        elif ext == 'avi':
            cmd.extend(['-c', 'copy'])
        else:
            # Default: stream copy
            cmd.extend(['-c', 'copy'])

        # Add output path with overwrite flag
        cmd.extend(['-y', output_path])

        return cmd


def get_strategy(output_path: str) -> FFmpegStrategy:
    """
    Factory function to get the appropriate FFmpeg strategy based on file extension.

    Args:
        output_path: The output file path to determine the format

    Returns:
        An instance of AudioStrategy or VideoStrategy based on the file extension
    """
    ext = os.path.splitext(output_path)[1].lower().lstrip('.')

    if ext in AudioStrategy.AUDIO_FORMATS:
        return AudioStrategy()
    else:
        return VideoStrategy()
