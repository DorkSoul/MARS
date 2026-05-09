import os
import time
import json
import uuid
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
    - Lazy disk writes (only when schedules are actually modified)
    """

    def __init__(self, config, browser_service):
        self.config = config
        self.browser_service = browser_service
        self.schedules = []
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self._dirty = False  # True when in-memory schedules differ from disk

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
        """Save schedules to disk (only if dirty)"""
        if not self._dirty:
            return
        try:
            with open(self.config.SCHEDULES_FILE, 'w') as f:
                json.dump(self.schedules, f, indent=2)
            self._dirty = False
        except Exception as e:
            logger.error(f"Error saving schedules: {e}")

    def _mark_dirty(self):
        """Mark schedules as needing a save."""
        self._dirty = True

    def add_schedule(self, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Add a new schedule"""
        with self.lock:
            schedule = {
                'id': uuid.uuid4().hex,
                'url': url,
                'name': name,
                'resolution': resolution,
                'framerate': framerate,
                'format': format,
                'start_time': start_time,
                'end_time': end_time,
                'repeat': repeat,
                'daily': daily,
                'status': 'pending',
                'next_check': None,
                'last_check': None,
                'created_at': datetime.now().isoformat()
            }
            self._update_next_check(schedule)
            self.schedules.append(schedule)
            self._mark_dirty()
            self.save_schedules()
            return schedule

    def remove_schedule(self, schedule_id):
        """Remove a schedule"""
        with self.lock:
            self.schedules = [s for s in self.schedules if s['id'] != schedule_id]
            self._mark_dirty()
            self.save_schedules()
            return True

    def update_schedule(self, schedule_id, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Update an existing schedule"""
        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    schedule['url'] = url
                    schedule['name'] = name
                    schedule['start_time'] = start_time
                    schedule['end_time'] = end_time
                    schedule['repeat'] = repeat
                    schedule['daily'] = daily
                    schedule['resolution'] = resolution
                    schedule['framerate'] = framerate
                    schedule['format'] = format
                    schedule['status'] = 'pending'
                    self._update_next_check(schedule)
                    self._mark_dirty()
                    self.save_schedules()
                    logger.info(f"Updated schedule {schedule_id}")
                    return schedule

            return None

    def move_to_next_slot(self, browser_id):
        """
        Move a schedule to its next time slot immediately after user stops download.

        When user manually stops a download, the schedule is reset to 'pending'
        and moved to the next occurrence (next day for daily, next week for weekly).
        """
        if not browser_id.startswith('sched_'):
            return False

        parts = browser_id.split('_')
        if len(parts) < 2:
            return False

        schedule_id = parts[1]

        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    if schedule.get('active_browser_id') == browser_id:
                        schedule['status'] = 'pending'
                        schedule['active_browser_id'] = None
                        schedule['manual_stop'] = False

                        if schedule.get('daily'):
                            logger.info(f"Moving daily schedule {schedule_id} to next day")
                            start_time_str = schedule['start_time']
                            start_hour, start_min = map(int, start_time_str.split(':'))
                            now = datetime.now()
                            tomorrow = now.date() + timedelta(days=1)
                            next_start = datetime.combine(tomorrow, datetime.min.time().replace(hour=start_hour, minute=start_min))
                            schedule['next_check'] = next_start.isoformat()
                            logger.info(f"Daily schedule {schedule_id} moved to {next_start}")
                        elif schedule.get('repeat'):
                            logger.info(f"Moving weekly schedule {schedule_id} to next week")
                            self._reschedule_next_week(schedule)
                        else:
                            logger.info(f"One-time schedule {schedule_id} stopped, marking as completed")
                            schedule['status'] = 'completed'
                            self._update_next_check(schedule)

                        self._mark_dirty()
                        self.save_schedules()
                        logger.info(f"Schedule {schedule_id} moved to next time slot (browser_id: {browser_id})")
                        return True

        return False

    def pause_schedule(self, schedule_id):
        """Toggle the paused state of a schedule."""
        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    currently_paused = schedule.get('paused', False)
                    schedule['paused'] = not currently_paused
                    if schedule['paused']:
                        schedule['status'] = 'paused'
                    else:
                        # Resuming — recalculate next check and set pending
                        schedule['status'] = 'pending'
                        self._update_next_check(schedule)
                    self._mark_dirty()
                    self.save_schedules()
                    logger.info(f"Schedule {schedule_id} {'paused' if schedule['paused'] else 'unpaused'}")
                    return schedule
        return None

    def get_schedules(self):
        """Get all schedules — active schedules sorted by next_check, paused schedules at the bottom."""
        sorted_schedules = sorted(
            self.schedules,
            key=lambda s: (
                s.get('paused', False),        # paused go last
                s.get('next_check') is None,
                s.get('next_check') or ''
            )
        )
        return sorted_schedules

    def refresh_all_schedule_times(self):
        """
        Reset all schedules as if they were just created.

        Clears all manual stops, resets statuses to pending,
        and recalculates next_check times.
        """
        with self.lock:
            count = 0
            for schedule in self.schedules:
                if schedule.get('paused', False):
                    continue  # don't disturb paused schedules
                schedule['status'] = 'pending'
                schedule['active_browser_id'] = None
                schedule['manual_stop'] = False
                schedule['last_check'] = None
                self._update_next_check(schedule)
                count += 1

            self._mark_dirty()
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

            for _ in range(30):
                if not self.running:
                    break
                time.sleep(1)

    def _check_schedules(self):
        """Check all schedules and run tasks if needed"""
        now = datetime.now()

        with self.lock:
            for schedule in self.schedules:
                # Skip paused schedules entirely
                if schedule.get('paused', False):
                    continue

                if schedule['status'] == 'completed' and not schedule.get('daily'):
                    continue

                # Skip schedules that are already being checked by a running thread
                if schedule.get('status') == 'checking':
                    continue

                try:
                    if schedule.get('daily'):
                        self._check_daily_schedule(schedule, now)
                    else:
                        start_dt = datetime.fromisoformat(schedule['start_time'])
                        end_dt = datetime.fromisoformat(schedule['end_time'])

                        if now > end_dt:
                            if schedule['repeat']:
                                self._reschedule_next_week(schedule)
                            else:
                                if schedule['status'] != 'download_started':
                                    schedule['status'] = 'completed'
                                schedule['active_browser_id'] = None
                                schedule['manual_stop'] = False
                            continue

                        if start_dt <= now <= end_dt:
                            if schedule['status'] == 'download_started':
                                active_browser_id = schedule.get('active_browser_id')
                                if self._is_download_active(active_browser_id):
                                    continue
                                else:
                                    logger.info(f"Download {active_browser_id} stopped for schedule {schedule['id']}, resuming stream checks")
                                    schedule['status'] = 'active'
                                    schedule['active_browser_id'] = None

                            if schedule['status'] != 'active':
                                next_check_val = schedule.get('next_check')
                                if next_check_val:
                                    try:
                                        next_check_dt = datetime.fromisoformat(next_check_val)
                                        if next_check_dt <= end_dt:
                                            schedule['status'] = 'active'
                                    except (ValueError, TypeError):
                                        schedule['status'] = 'active'
                                else:
                                    schedule['status'] = 'active'

                            next_check = schedule.get('next_check')
                            if not next_check or now >= datetime.fromisoformat(next_check):
                                self._perform_check(schedule)

                        elif now < start_dt:
                            schedule['status'] = 'pending'
                            next_check = schedule.get('next_check')
                            if not next_check:
                                self._update_next_check(schedule)
                            else:
                                try:
                                    next_check_dt = datetime.fromisoformat(next_check)
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
        - Status transitions (pending -> active -> checking -> download_started)
        - Auto-resume on download failures (unless manually stopped)
        - Proper reset when time window ends
        """
        start_time_str = schedule['start_time']
        end_time_str = schedule['end_time']

        today = now.date()
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))

        start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
        end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

        spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

        if spans_midnight:
            if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                yesterday = today - timedelta(days=1)
                start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
            else:
                end_dt = end_dt + timedelta(days=1)

        if start_dt <= now <= end_dt:
            if schedule['status'] == 'download_started':
                active_browser_id = schedule.get('active_browser_id')
                if self._is_download_active(active_browser_id):
                    return
                else:
                    logger.info(f"Download {active_browser_id} stopped for schedule {schedule['id']}, resuming stream checks")
                    schedule['status'] = 'active'
                    schedule['active_browser_id'] = None

            if schedule['status'] != 'active':
                next_check_val = schedule.get('next_check')
                if next_check_val:
                    try:
                        next_check_dt = datetime.fromisoformat(next_check_val)
                        if next_check_dt <= end_dt:
                            schedule['status'] = 'active'
                    except (ValueError, TypeError):
                        schedule['status'] = 'active'
                else:
                    schedule['status'] = 'active'

            next_check = schedule.get('next_check')
            if not next_check or now >= datetime.fromisoformat(next_check):
                self._perform_check(schedule)

        elif now < start_dt:
            schedule['status'] = 'pending'
            next_check = schedule.get('next_check')
            if not next_check:
                self._update_next_check(schedule)
            else:
                try:
                    next_check_dt = datetime.fromisoformat(next_check)
                    if next_check_dt < now:
                        self._update_next_check(schedule)
                except (ValueError, TypeError):
                    self._update_next_check(schedule)

        else:
            if schedule['status'] in ['active', 'download_started', 'checking']:
                schedule['status'] = 'pending'
                schedule['last_check'] = None
                schedule['active_browser_id'] = None
                schedule['manual_stop'] = False
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
            start_time_str = schedule['start_time']
            end_time_str = schedule['end_time']

            today = now.date()
            start_hour, start_min = map(int, start_time_str.split(':'))
            end_hour, end_min = map(int, end_time_str.split(':'))

            start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
            end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

            spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

            if spans_midnight:
                if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    yesterday = today - timedelta(days=1)
                    start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                    end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
                else:
                    end_dt = end_dt + timedelta(days=1)

            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = min(now + timedelta(minutes=minutes), end_dt)
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
            else:
                if spans_midnight and now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    next_start = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
                else:
                    tomorrow = today + timedelta(days=1)
                    next_start = datetime.combine(tomorrow, datetime.min.time().replace(hour=start_hour, minute=start_min))

                schedule['next_check'] = next_start.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to next window start: {next_start}")

        else:
            start_dt = datetime.fromisoformat(schedule['start_time'])
            end_dt = datetime.fromisoformat(schedule['end_time'])

            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = min(now + timedelta(minutes=minutes), end_dt)
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
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
        schedule['active_browser_id'] = None
        schedule['manual_stop'] = False

        self._update_next_check(schedule)
        logger.info(f"Rescheduled {schedule['id']} to next week: {new_start}")

    def _is_download_active(self, browser_id):
        """
        Check if a specific download is still active.

        Returns True if the download exists in the queue and has no completed_at.
        """
        try:
            if not browser_id:
                return False

            download_queue = self.browser_service.download_service.download_queue

            if browser_id in download_queue:
                download_info = download_queue[browser_id]
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
        """Perform the actual browser check for a schedule.

        Sets status to 'checking' before spawning the thread to prevent
        duplicate check threads from being spawned on subsequent loop iterations.
        """
        # Guard: mark as checking before the thread starts
        schedule['status'] = 'checking'
        self._mark_dirty()

        duration = random.uniform(20, 60)

        check_thread = threading.Thread(
            target=self._run_browser_check_task,
            args=(schedule, duration),
            daemon=True,
        )
        check_thread.start()

        # Update next check time so the loop doesn't re-trigger immediately
        self._update_next_check(schedule)

    def _run_browser_check_task(self, schedule, duration):
        """The actual browser check task running in a separate thread."""
        browser_id = f"sched_{schedule['id']}_{int(time.time())}"

        try:
            logger.info(f"Requesting browser for schedule {schedule['id']} (will queue if needed)")
            filename_prefix = schedule.get('name') if schedule.get('name') else None
            success, detector = self.browser_service.start_browser(
                url=schedule['url'],
                browser_id=browser_id,
                auto_download=True,
                filename=filename_prefix,
                resolution=schedule.get('resolution', '1080p'),
                framerate=schedule.get('framerate', 'any'),
                output_format=schedule.get('format', 'mp4')
            )

            if not success:
                logger.warning(f"Failed to start browser for schedule {schedule['id']}")
                # Revert status so next loop can retry
                with self.lock:
                    for s in self.schedules:
                        if s['id'] == schedule['id'] and s.get('status') == 'checking':
                            s['status'] = 'active'
                            self._mark_dirty()
                            break
                return

            start_wait = time.time()
            while time.time() - start_wait < duration:
                status = self.browser_service.get_browser_status(browser_id)
                if not status:
                    break

                dl_status = self.browser_service.download_service.get_download_status(browser_id)
                if dl_status:
                    logger.info(f"Download started for schedule {schedule['id']}! (browser_id: {browser_id})")

                    with self.lock:
                        for s in self.schedules:
                            if s['id'] == schedule['id']:
                                s['status'] = 'download_started'
                                s['active_browser_id'] = browser_id
                                self._mark_dirty()
                                self.save_schedules()
                                break

                    break

                time.sleep(1)

            # If no download started, revert to 'active' so next window check can retry
            with self.lock:
                for s in self.schedules:
                    if s['id'] == schedule['id'] and s.get('status') == 'checking':
                        s['status'] = 'active'
                        self._mark_dirty()
                        break

            logger.info(f"Closing browser for schedule {schedule['id']}")
            self.browser_service.close_browser(browser_id)

        except Exception as e:
            logger.error(f"Error in browser check task: {e}")
            # Revert checking status on error
            with self.lock:
                for s in self.schedules:
                    if s['id'] == schedule['id'] and s.get('status') == 'checking':
                        s['status'] = 'active'
                        self._mark_dirty()
                        break
            try:
                self.browser_service.close_browser(browser_id)
            except Exception:
                pass
