import json
import time
import logging
from flask import Blueprint, Response, stream_with_context

logger = logging.getLogger(__name__)

events_bp = Blueprint('events', __name__, url_prefix='/api/events')


def init_events_routes(browser_service, download_service):
    """Initialize SSE event-stream routes."""

    @events_bp.route('/browser/<browser_id>')
    def browser_events(browser_id):
        """
        SSE stream for a specific browser/download session.

        Replaces polling on /api/browser/status/<browser_id>.
        Closes automatically when the browser/download is no longer running.
        """
        def generate():
            while True:
                try:
                    status = browser_service.get_browser_status(browser_id)

                    if status is None:
                        # Check direct download status as fallback
                        with download_service._queue_lock:
                            direct = download_service.direct_download_status.get(browser_id)
                        if direct:
                            status = dict(direct)
                        else:
                            # Browser gone — send a final closed event and stop
                            yield f"data: {json.dumps({'is_running': False, 'closed': True})}\n\n"
                            return

                    # Attach download info if available
                    download_info = download_service.get_download_status(browser_id)
                    if download_info:
                        status['download'] = download_info

                    yield f"data: {json.dumps(status)}\n\n"

                    # Stop streaming once the browser/download has finished
                    if not status.get('is_running', True):
                        return

                except Exception as e:
                    logger.error(f"SSE error for browser {browser_id}: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

                time.sleep(2)

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

    @events_bp.route('/active')
    def active_events():
        """
        SSE stream for the active downloads list.

        Streams a compact (no thumbnail data) snapshot every 3 seconds.
        Thumbnails are still fetched on demand via /api/browser/status/<id>.
        """
        def generate():
            while True:
                try:
                    active = download_service.get_active_downloads()
                    # Strip bulky thumbnail data to keep the SSE stream lightweight
                    compact = [
                        {k: v for k, v in d.items() if k != 'thumbnail'}
                        for d in active
                    ]
                    yield f"data: {json.dumps({'active_downloads': compact})}\n\n"
                except Exception as e:
                    logger.error(f"SSE active events error: {e}")
                time.sleep(3)

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

    return events_bp
