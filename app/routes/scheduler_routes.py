import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/api/schedules')

def init_scheduler_routes(scheduler):
    """Initialize scheduler routes with scheduler service"""

    @scheduler_bp.route('/', methods=['GET'])
    def list_schedules():
        """List all schedules"""
        try:
            schedules = scheduler.get_schedules()
            return jsonify(schedules)
        except Exception as e:
            logger.error(f"Error listing schedules: {e}")
            return jsonify({'error': str(e)}), 500

    @scheduler_bp.route('/', methods=['POST'])
    def add_schedule():
        """Add a new schedule"""
        try:
            data = request.json
            url = data.get('url')
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            repeat = data.get('repeat', False)
            daily = data.get('daily', False)
            name = data.get('name')
            resolution = data.get('resolution', '1080p')
            framerate = data.get('framerate', 'any')
            format = data.get('format', 'mp4')

            if not all([url, start_time, end_time]):
                return jsonify({'error': 'Missing required fields'}), 400

            schedule = scheduler.add_schedule(url, start_time, end_time, repeat, daily, name, resolution, framerate, format)

            return jsonify({
                'success': True,
                'schedule': schedule,
                'message': 'Schedule added successfully'
            })

        except Exception as e:
            logger.error(f"Error adding schedule: {e}")
            return jsonify({'error': str(e)}), 500

    @scheduler_bp.route('/<schedule_id>', methods=['DELETE'])
    def delete_schedule(schedule_id):
        """Delete a schedule"""
        try:
            if scheduler.remove_schedule(schedule_id):
                return jsonify({'success': True, 'message': 'Schedule removed'})
            else:
                return jsonify({'error': 'Schedule not found'}), 404
        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            return jsonify({'error': str(e)}), 500

    @scheduler_bp.route('/<schedule_id>', methods=['PUT'])
    def update_schedule(schedule_id):
        """Update an existing schedule"""
        try:
            data = request.json
            url = data.get('url')
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            repeat = data.get('repeat', False)
            daily = data.get('daily', False)
            name = data.get('name')
            resolution = data.get('resolution', '1080p')
            framerate = data.get('framerate', 'any')
            format = data.get('format', 'mp4')

            if not all([url, start_time, end_time]):
                return jsonify({'error': 'Missing required fields'}), 400

            updated = scheduler.update_schedule(
                schedule_id, url, start_time, end_time,
                repeat, daily, name, resolution, framerate, format
            )

            if updated:
                return jsonify({
                    'success': True,
                    'schedule': updated,
                    'message': 'Schedule updated successfully'
                })
            else:
                return jsonify({'error': 'Schedule not found'}), 404

        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            return jsonify({'error': str(e)}), 500

    @scheduler_bp.route('/refresh', methods=['POST'])
    def refresh_schedules():
        """Force refresh all schedule next_check times"""
        try:
            count = scheduler.refresh_all_schedule_times()
            return jsonify({
                'success': True,
                'message': f'Refreshed {count} schedules',
                'count': count
            })
        except Exception as e:
            logger.error(f"Error refreshing schedules: {e}")
            return jsonify({'error': str(e)}), 500

    return scheduler_bp
