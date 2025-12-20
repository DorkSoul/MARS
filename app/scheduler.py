import os
import time
import json
import logging
import threading
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Scheduler:
    """
    Manages scheduled stream checks with intelligent retry and resilience.

    Features:
    - Daily and weekly recurring schedules
    - Auto-resume on stream failures within time windows
    - Manual stop detection and handling
    - Specific download tracking for multi-stream support
    - Thread-safe schedule management with JSON persistence
    """

    def __init__(self, config, browser_service):
        self.config = config
        self.browser_service = browser_service
        self.schedules = []
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        self.load_schedules()

    def load_schedules(self):
        """Load schedules from disk"""
        if os.path.exists(self.config.SCHEDULES_FILE):
            try:
                with open(self.config.SCHEDULES_FILE, 'r') as f:
                    self.schedules = json.load(f)
                logger.info(f"Loaded {len(self.schedules)} schedules")

                # Ensure all schedules have next_check calculated
                for schedule in self.schedules:
                    if not schedule.get('next_check'):
                        self._update_next_check(schedule)

            except Exception as e:
                logger.error(f"Error loading schedules: {e}")
                self.schedules = []
        else:
            self.schedules = []

    def save_schedules(self):
        """Save schedules to disk"""
        try:
            with open(self.config.SCHEDULES_FILE, 'w') as f:
                json.dump(self.schedules, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving schedules: {e}")

    def add_schedule(self, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Add a new schedule"""
        with self.lock:
            schedule = {
                'id': str(int(time.time() * 1000)),
                'url': url,
                'name': name,  # Optional name for filename prefix (not defaulting to URL)
                'resolution': resolution,
                'framerate': framerate,
                'format': format,
                'start_time': start_time, # ISO format string or HH:MM for daily
                'end_time': end_time,     # ISO format string or HH:MM for daily
                'repeat': repeat,
                'daily': daily,           # If true, start_time and end_time are HH:MM format
                'status': 'pending',      # pending, active, completed, download_started
                'next_check': None,
                'last_check': None,
                'created_at': datetime.now().isoformat()
            }
            # Initialize next check
            self._update_next_check(schedule)

            self.schedules.append(schedule)
            self.save_schedules()
            return schedule

    def remove_schedule(self, schedule_id):
        """Remove a schedule"""
        with self.lock:
            self.schedules = [s for s in self.schedules if s['id'] != schedule_id]
            self.save_schedules()
            return True

    def update_schedule(self, schedule_id, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Update an existing schedule"""
        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    # Update fields
                    schedule['url'] = url
                    schedule['name'] = name  # Optional name, not defaulting to URL
                    schedule['start_time'] = start_time
                    schedule['end_time'] = end_time
                    schedule['repeat'] = repeat
                    schedule['daily'] = daily
                    schedule['resolution'] = resolution
                    schedule['framerate'] = framerate
                    schedule['format'] = format

                    # Reset status if times changed
                    schedule['status'] = 'pending'

                    # Update next check time
                    self._update_next_check(schedule)

                    self.save_schedules()
                    logger.info(f"Updated schedule {schedule_id}")
                    return schedule

            return None

    def move_to_next_slot(self, browser_id):
        """
        Move a schedule to its next time slot immediately after user stops download.

        When user manually stops a download, the schedule is reset to 'pending'
        and moved to the next occurrence (next day for daily, next week for weekly).

        Args:
            browser_id: The browser_id of the stopped download

        Returns:
            bool: True if schedule was found and moved, False otherwise
        """
        # Check if this is a scheduled download (format: sched_{schedule_id}_{timestamp})
        if not browser_id.startswith('sched_'):
            return False

        # Extract schedule_id from browser_id
        parts = browser_id.split('_')
        if len(parts) < 2:
            return False

        schedule_id = parts[1]

        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    # Only process if this is the active browser_id
                    if schedule.get('active_browser_id') == browser_id:
                        # Reset schedule state
                        schedule['status'] = 'pending'
                        schedule['active_browser_id'] = None
                        schedule['manual_stop'] = False

                        # Move to next time slot
                        if schedule.get('daily'):
                            # Daily schedule - explicitly move to tomorrow's start time
                            logger.info(f"Moving daily schedule {schedule_id} to next day")
                            start_time_str = schedule['start_time']
                            start_hour, start_min = map(int, start_time_str.split(':'))

                            # Calculate tomorrow's start time
                            now = datetime.now()
                            tomorrow = now.date() + timedelta(days=1)
                            next_start = datetime.combine(tomorrow, datetime.min.time().replace(hour=start_hour, minute=start_min))

                            schedule['next_check'] = next_start.isoformat()
                            logger.info(f"Daily schedule {schedule_id} moved to {next_start}")
                        elif schedule.get('repeat'):
                            # Weekly recurring - move to next week
                            logger.info(f"Moving weekly schedule {schedule_id} to next week")
                            self._reschedule_next_week(schedule)
                        else:
                            # One-time schedule - mark as completed
                            logger.info(f"One-time schedule {schedule_id} stopped, marking as completed")
                            schedule['status'] = 'completed'
                            self._update_next_check(schedule)

                        self.save_schedules()
                        logger.info(f"Schedule {schedule_id} moved to next time slot (browser_id: {browser_id})")
                        return True

        return False

    def get_schedules(self):
        """Get all schedules, sorted by next_check time"""
        # Sort schedules by next_check time (soonest first)
        # Schedules without next_check go to the end
        sorted_schedules = sorted(
            self.schedules,
            key=lambda s: (
                s.get('next_check') is None,  # False (0) for schedules with next_check, True (1) for those without
                s.get('next_check') or ''      # Sort by next_check if it exists
            )
        )
        return sorted_schedules

    def refresh_all_schedule_times(self):
        """
        Reset all schedules as if they were just created.

        This clears all manual stops, resets statuses to pending,
        and recalculates next_check times. If a schedule's time window
        is currently active, it will start checking for streams again.
        """
        with self.lock:
            count = 0
            for schedule in self.schedules:
                # Reset schedule state completely
                schedule['status'] = 'pending'
                schedule['active_browser_id'] = None
                schedule['manual_stop'] = False
                schedule['last_check'] = None

                # Recalculate next_check time
                self._update_next_check(schedule)
                count += 1

            self.save_schedules()
            logger.info(f"Reset {count} schedules to fresh state")
            return count

    def start(self):
        """Start the scheduler loop"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            logger.info("Scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop"""
        logger.info("Scheduler loop running")
        while self.running:
            try:
                self._check_schedules()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            # Sleep for a bit before next iteration (e.g., 30 seconds)
            # We don't need super high precision
            for _ in range(30):
                if not self.running: 
                    break
                time.sleep(1)

    def _check_schedules(self):
        """Check all schedules and run tasks if needed"""
        now = datetime.now()

        with self.lock:
            for schedule in self.schedules:
                if schedule['status'] == 'completed' and not schedule.get('daily'):
                    # Skip completed non-daily schedules
                    continue

                try:
                    if schedule.get('daily'):
                        # Daily schedule - handle time-based windows
                        self._check_daily_schedule(schedule, now)
                    else:
                        # Regular schedule - handle datetime-based windows
                        start_dt = datetime.fromisoformat(schedule['start_time'])
                        end_dt = datetime.fromisoformat(schedule['end_time'])

                        # Check if window passed
                        if now > end_dt:
                            if schedule['repeat']:
                                # Move to next week
                                self._reschedule_next_week(schedule)
                            else:
                                if schedule['status'] != 'download_started':
                                    schedule['status'] = 'completed'
                                # Clear flags when window ends
                                schedule['active_browser_id'] = None
                                schedule['manual_stop'] = False
                            continue

                        # Check if currently active window
                        if start_dt <= now <= end_dt:
                            if schedule['status'] == 'download_started':
                                # Check if the specific download is still active
                                active_browser_id = schedule.get('active_browser_id')
                                if self._is_download_active(active_browser_id):
                                    # Download still running, keep status and skip check
                                    continue
                                else:
                                    # Download crashed/failed automatically - resume checking
                                    logger.info(f"Download {active_browser_id} stopped for schedule {schedule['id']}, resuming stream checks")
                                    schedule['status'] = 'active'
                                    schedule['active_browser_id'] = None
                                    # Will proceed to check stream below

                            # Ensure status is active, but only if next_check is within current window
                            if schedule['status'] != 'active':
                                next_check_val = schedule.get('next_check')
                                if next_check_val:
                                    try:
                                        next_check_dt = datetime.fromisoformat(next_check_val)
                                        # Only change to active if next_check is not beyond current window
                                        if next_check_dt <= end_dt:
                                            schedule['status'] = 'active'
                                    except (ValueError, TypeError):
                                        schedule['status'] = 'active'
                                else:
                                    schedule['status'] = 'active'

                            # Check if it's time to check stream
                            next_check = schedule.get('next_check')
                            if not next_check or now >= datetime.fromisoformat(next_check):
                                # It's time! (when next_check time arrives)
                                self._perform_check(schedule)

                        elif now < start_dt:
                             schedule['status'] = 'pending'
                             # Ensure next_check is set (only if missing or in the past)
                             next_check = schedule.get('next_check')
                             if not next_check:
                                 self._update_next_check(schedule)
                             else:
                                 try:
                                     next_check_dt = datetime.fromisoformat(next_check)
                                     # Only recalculate if next_check is in the past
                                     if next_check_dt < now:
                                         self._update_next_check(schedule)
                                 except (ValueError, TypeError):
                                     self._update_next_check(schedule)

                except Exception as e:
                    logger.error(f"Error processing schedule {schedule['id']}: {e}")

            self.save_schedules()

    def _check_daily_schedule(self, schedule, now):
        """
        Check a daily schedule (time-based, repeats every day).

        Handles:
        - Midnight-spanning windows (e.g., 23:00-01:00)
        - Status transitions (pending -> active -> download_started)
        - Auto-resume on download failures (unless manually stopped)
        - Proper reset when time window ends
        """
        # Parse the time strings (format: "HH:MM")
        start_time_str = schedule['start_time']
        end_time_str = schedule['end_time']

        # Get today's date
        today = now.date()

        # Create datetime objects for today's window
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))

        start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
        end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

        # Detect if this is a midnight-spanning window (e.g., 23:00 - 01:00)
        spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

        if spans_midnight:
            # For midnight-spanning windows, we need to check if we're in yesterday's window
            # that extends into today, OR in today's window that extends into tomorrow

            # Check if we're in yesterday's window (before today's start time)
            if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                # We're in the early morning hours - check if yesterday's window extends to now
                yesterday = today - timedelta(days=1)
                start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
            else:
                # We're after start time today - window extends into tomorrow
                end_dt = end_dt + timedelta(days=1)
        else:
            # Normal same-day window
            pass

        # Check if we're currently in the active window
        if start_dt <= now <= end_dt:
            if schedule['status'] == 'download_started':
                # Check if the specific download is still active
                active_browser_id = schedule.get('active_browser_id')
                if self._is_download_active(active_browser_id):
                    # Download still running, keep status and skip check
                    return
                else:
                    # Download crashed/failed automatically - resume checking
                    logger.info(f"Download {active_browser_id} stopped for schedule {schedule['id']}, resuming stream checks")
                    schedule['status'] = 'active'
                    schedule['active_browser_id'] = None
                    # Will proceed to check stream below

            # Ensure status is active, but only if next_check is within current window
            if schedule['status'] != 'active':
                next_check_val = schedule.get('next_check')
                if next_check_val:
                    try:
                        next_check_dt = datetime.fromisoformat(next_check_val)
                        # Only change to active if next_check is not beyond current window
                        if next_check_dt <= end_dt:
                            schedule['status'] = 'active'
                    except (ValueError, TypeError):
                        schedule['status'] = 'active'
                else:
                    schedule['status'] = 'active'

            # Check if it's time to check stream
            next_check = schedule.get('next_check')
            if not next_check or now >= datetime.fromisoformat(next_check):
                # It's time! (when next_check time arrives)
                self._perform_check(schedule)

        elif now < start_dt:
            # Window hasn't started yet
            schedule['status'] = 'pending'
            # Ensure next_check is set (only if missing or in the past)
            next_check = schedule.get('next_check')
            if not next_check:
                self._update_next_check(schedule)
            else:
                try:
                    next_check_dt = datetime.fromisoformat(next_check)
                    # Only recalculate if next_check is in the past
                    if next_check_dt < now:
                        self._update_next_check(schedule)
                except (ValueError, TypeError):
                    self._update_next_check(schedule)

        else:
            # Window has passed - always reset to pending for next day
            if schedule['status'] in ['active', 'download_started']:
                # Reset for next day
                schedule['status'] = 'pending'
                schedule['last_check'] = None
                schedule['active_browser_id'] = None  # Clear tracked browser_id
                schedule['manual_stop'] = False  # Clear manual stop flag for next time window
                self._update_next_check(schedule)

    def _update_next_check(self, schedule):
        """
        Calculate next check time based on schedule window.

        Logic:
        - Before window: Schedule check at window start
        - During window: Random 5-8 minute intervals
        - After window: Schedule for next occurrence (daily/weekly)
        - Handles midnight-spanning windows correctly
        """
        now = datetime.now()

        if schedule.get('daily'):
            # Daily schedule - calculate based on time
            start_time_str = schedule['start_time']
            end_time_str = schedule['end_time']

            today = now.date()
            start_hour, start_min = map(int, start_time_str.split(':'))
            end_hour, end_min = map(int, end_time_str.split(':'))

            start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
            end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

            # Detect if this is a midnight-spanning window (e.g., 23:00 - 01:00)
            spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

            if spans_midnight:
                # For midnight-spanning windows, determine which window we're checking
                if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    # We're in the early morning hours - check if yesterday's window extends to now
                    yesterday = today - timedelta(days=1)
                    start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                    end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
                else:
                    # We're after start time today - window extends into tomorrow
                    end_dt = end_dt + timedelta(days=1)

            # If window hasn't started yet, schedule check for start of window
            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            # If we're in the window, schedule random check in 5-8 minutes
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = now + timedelta(minutes=minutes)
                # Make sure we don't schedule past the end of the window
                if next_dt > end_dt:
                    next_dt = end_dt
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
            # If window has passed, schedule for next occurrence
            else:
                # For midnight-spanning, if we're past end time but before start time,
                # the next window is today (later). Otherwise it's tomorrow.
                if spans_midnight and now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    # We're past yesterday's window end, next window is today
                    next_start = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
                else:
                    # Next window is tomorrow
                    tomorrow = today + timedelta(days=1)
                    next_start = datetime.combine(tomorrow, datetime.min.time().replace(hour=start_hour, minute=start_min))

                schedule['next_check'] = next_start.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to next window start: {next_start}")

        else:
            # Regular schedule - calculate based on datetime
            start_dt = datetime.fromisoformat(schedule['start_time'])
            end_dt = datetime.fromisoformat(schedule['end_time'])

            # If window hasn't started yet, schedule check for start of window
            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            # If we're in the window, schedule random check in 5-8 minutes
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = now + timedelta(minutes=minutes)
                # Make sure we don't schedule past the end of the window
                if next_dt > end_dt:
                    next_dt = end_dt
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
            # If window has passed, clear next_check (will be rescheduled)
            else:
                schedule['next_check'] = None
                logger.debug(f"Schedule {schedule['id']}: window passed, clearing next_check")

    def _reschedule_next_week(self, schedule):
        """Move schedule to next week"""
        start_dt = datetime.fromisoformat(schedule['start_time'])
        end_dt = datetime.fromisoformat(schedule['end_time'])

        new_start = start_dt + timedelta(days=7)
        new_end = end_dt + timedelta(days=7)

        schedule['start_time'] = new_start.isoformat()
        schedule['end_time'] = new_end.isoformat()
        schedule['status'] = 'pending'
        schedule['active_browser_id'] = None  # Clear tracked browser_id
        schedule['manual_stop'] = False  # Clear manual stop flag for next time window

        # Update next_check to the new window start
        self._update_next_check(schedule)

        logger.info(f"Rescheduled {schedule['id']} to next week: {new_start}")

    def _is_download_active(self, browser_id):
        """
        Check if a specific download is still active.

        A download is considered active if it exists in the download_queue
        and doesn't have a 'completed_at' timestamp.

        Args:
            browser_id: The specific browser_id to check

        Returns:
            bool: True if the download is still active, False otherwise
        """
        try:
            if not browser_id:
                return False

            download_queue = self.browser_service.download_service.download_queue

            if browser_id in download_queue:
                download_info = download_queue[browser_id]
                # Check if download is still active (no completed_at)
                is_active = 'completed_at' not in download_info
                if is_active:
                    logger.debug(f"Download {browser_id} is still active")
                else:
                    logger.debug(f"Download {browser_id} has completed")
                return is_active
            else:
                logger.debug(f"Download {browser_id} not found in queue")
                return False

        except Exception as e:
            logger.error(f"Error checking download status for {browser_id}: {e}")
            return False

    def _perform_check(self, schedule):
        """Perform the actual browser check"""
        logger.info(f"Performing scheduled check for {schedule['name']} ({schedule['url']})")
        
        # Determine duration (20-60s)
        duration = random.uniform(20, 60)
        
        # Thread logic for the check so we don't block main scheduler loop for a minute
        check_thread = threading.Thread(
            target=self._run_browser_check_task,
            args=(schedule, duration)
        )
        check_thread.start()
        
        # Update next check time immediately so we don't spawn multiple
        self._update_next_check(schedule)

    def _run_browser_check_task(self, schedule, duration):
        """The actual task running in a separate thread"""
        browser_id = f"sched_{schedule['id']}_{int(time.time())}"

        try:
            # Queue browser (will wait for previous browsers to close)
            logger.info(f"Requesting browser for schedule {schedule['id']} (will queue if needed)")
            # Use schedule name as filename prefix (without extension)
            # This will be combined with timestamp in the filename generator
            filename_prefix = schedule.get('name') if schedule.get('name') else None
            success, detector = self.browser_service.start_browser(
                url=schedule['url'],
                browser_id=browser_id,
                auto_download=True, # Important!
                filename=filename_prefix,  # Pass name for prefix
                resolution=schedule.get('resolution', '1080p'),
                framerate=schedule.get('framerate', 'any'),
                output_format=schedule.get('format', 'mp4')
            )
            
            if not success:
                logger.warning(f"Failed to start browser for schedule {schedule['id']}")
                return

            # Monitor browser for stream detection (up to specified duration)
            start_wait = time.time()
            while time.time() - start_wait < duration:
                status = self.browser_service.get_browser_status(browser_id)
                if not status:
                    break

                # Check if download has started via download service
                dl_status = self.browser_service.download_service.get_download_status(browser_id)
                if dl_status:
                    logger.info(f"Download started for schedule {schedule['id']}! (browser_id: {browser_id})")

                    with self.lock:
                        for s in self.schedules:
                            if s['id'] == schedule['id']:
                                s['status'] = 'download_started'
                                s['active_browser_id'] = browser_id
                                self.save_schedules()
                                break

                    # Download started successfully, exit monitoring loop
                    break

                time.sleep(1)

            # Close browser after monitoring completes
            logger.info(f"Closing browser for schedule {schedule['id']}")
            self.browser_service.close_browser(browser_id)

        except Exception as e:
            logger.error(f"Error in browser check task: {e}")
            try:
                self.browser_service.close_browser(browser_id)
            except:
                pass
